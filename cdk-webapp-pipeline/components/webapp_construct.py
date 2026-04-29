from dataclasses import dataclass, field
from aws_cdk import (
    Duration,
    RemovalPolicy,
    SecretValue,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_targets as targets,
    aws_iam as iam,
    aws_ssm as ssm,
    aws_s3 as s3,
    aws_codedeploy as codedeploy,
)
from constructs import Construct


@dataclass
class WebappProps:
    """
    WebappConstruct に渡す設定値をまとめた Props クラス。
    alb-ec2-rds-webapp の CloudFormation Parameters に相当する。
    """
    employee_id: str
    my_ip: str
    db_password: str
    key_name: str
    tomcat_version: str = field(default="10.1.28")


class WebappConstruct(Construct):
    """
    ALB + EC2(Tomcat + Spring Boot) + RDS の3層Webアーキテクチャをカプセル化した Construct。

    alb-ec2-rds-webapp（CloudFormation版）との主な違い:
      - WAR はパイプラインの CodeDeploy ステップがデプロイする（UserData では配置しない）
      - EC2 UserData に CodeDeploy エージェントのインストールを追加
      - ALB ヘルスチェックは WAR デプロイ前の 404 も許容する

    --- 公開属性 ---
      self.alb              : ApplicationLoadBalancer
      self.instance         : Instance (EC2)
      self.db_instance      : DatabaseInstance (RDS)
      self.vpc              : Vpc
      self.artifact_bucket  : Bucket (CodeDeploy デプロイバンドル置き場)
      self.deploy_application : ServerApplication (CodeDeploy)
      self.deployment_group   : ServerDeploymentGroup (CodeDeploy)
    """

    def __init__(self, scope: Construct, id: str, *, props: WebappProps) -> None:
        super().__init__(scope, id)

        prefix = f"{props.employee_id}-cdk4"

        # ============================================================
        # VPC
        # ============================================================
        self.vpc = ec2.Vpc(
            self, "VPC",
            vpc_name=f"{prefix}-vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # S3 VPC エンドポイント（EC2 が S3 からデプロイバンドルを取得するために使用）
        self.vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )

        # ============================================================
        # Security Groups
        # ============================================================
        alb_sg = ec2.SecurityGroup(
            self, "ALBSecurityGroup",
            vpc=self.vpc,
            security_group_name=f"{prefix}-alb-sg",
            description=f"{prefix} ALB SG",
        )
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "HTTP from internet")

        ec2_sg = ec2.SecurityGroup(
            self, "EC2SecurityGroup",
            vpc=self.vpc,
            security_group_name=f"{prefix}-ec2-sg",
            description=f"{prefix} EC2 Tomcat SG",
        )
        ec2_sg.add_ingress_rule(alb_sg, ec2.Port.tcp(8080), "Tomcat from ALB SG only (SG-to-SG)")
        ec2_sg.add_ingress_rule(ec2.Peer.ipv4(props.my_ip), ec2.Port.tcp(22), "SSH from my IP")

        rds_sg = ec2.SecurityGroup(
            self, "RDSSecurityGroup",
            vpc=self.vpc,
            security_group_name=f"{prefix}-rds-sg",
            description=f"{prefix} RDS MySQL SG",
        )
        rds_sg.add_ingress_rule(ec2_sg, ec2.Port.tcp(3306), "MySQL from EC2 SG only (SG-to-SG)")

        # ============================================================
        # SSM Parameter Store
        # ============================================================
        ssm.StringParameter(
            self, "DBPasswordParam",
            parameter_name=f"/{props.employee_id}/cdk4/db-password",
            string_value=props.db_password,
            description=f"RDS MySQL master password for {prefix}",
        )

        # ============================================================
        # S3 Artifact Bucket
        # CodeDeploy デプロイバンドル（WAR + appspec.yml + scripts）の置き場
        # ============================================================
        self.artifact_bucket = s3.Bucket(
            self, "ArtifactBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        # ============================================================
        # RDS MySQL
        # ============================================================
        self.db_instance = rds.DatabaseInstance(
            self, "RDSInstance",
            database_name="sampledb",
            engine=rds.DatabaseInstanceEngine.mysql(
                version=rds.MysqlEngineVersion.VER_8_0,
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.MICRO,
            ),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
            ),
            security_groups=[rds_sg],
            credentials=rds.Credentials.from_username(
                "admin",
                password=SecretValue.unsafe_plain_text(props.db_password),
            ),
            instance_identifier=f"{prefix}-rds-mysql",
            multi_az=False,
            publicly_accessible=False,
            allocated_storage=20,
            backup_retention=Duration.days(0),
            delete_automated_backups=True,
            deletion_protection=False,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ============================================================
        # IAM Role for EC2
        # ============================================================
        ec2_role = iam.Role(
            self, "EC2Role",
            role_name=f"{prefix}-ec2-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMReadOnlyAccess"),
            ],
        )
        # CodeDeploy が S3 からデプロイバンドルを取得するために EC2 ロールに S3 読み取り権限を付与
        self.artifact_bucket.grant_read(ec2_role)

        # ============================================================
        # EC2 UserData
        # alb-ec2-rds-webapp との違い:
        #   - WAR は UserData でダウンロードしない（CodeDeploy が後から配置する）
        #   - CodeDeploy エージェントをインストールする
        #   - ALB ヘルスチェックのため Tomcat だけ起動しておく
        # ============================================================
        rds_endpoint = self.db_instance.db_instance_endpoint_address

        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "set -xe",
            "exec > >(tee /var/log/user-data.log) 2>&1",

            # Java 17 + Tomcat インストール
            "dnf install -y java-17-amazon-corretto wget ruby",
            "cd /opt",
            f"wget -q https://archive.apache.org/dist/tomcat/tomcat-10/v{props.tomcat_version}/bin/apache-tomcat-{props.tomcat_version}.tar.gz",
            f"tar xzf apache-tomcat-{props.tomcat_version}.tar.gz",
            f"mv apache-tomcat-{props.tomcat_version} tomcat",
            "chmod +x /opt/tomcat/bin/*.sh",

            # DB 接続情報を setenv.sh に書き込む
            # DB_HOST: CloudFormation が RDS エンドポイントを解決して埋め込む
            # DB_PASSWORD: 実行時に SSM から取得する
            f"DB_PASSWORD=$(aws ssm get-parameter --name '/{props.employee_id}/cdk4/db-password' --query Parameter.Value --output text --region ap-northeast-1)",
            f"echo 'export DB_HOST={rds_endpoint}' > /opt/tomcat/bin/setenv.sh",
            'echo "export DB_PASSWORD=$DB_PASSWORD" >> /opt/tomcat/bin/setenv.sh',
            "chmod +x /opt/tomcat/bin/setenv.sh",

            # CodeDeploy エージェントをインストール
            # WAR のデプロイは後でパイプラインの CodeDeploy ステップが行う
            "wget -O /tmp/install_codedeploy https://aws-codedeploy-ap-northeast-1.s3.ap-northeast-1.amazonaws.com/latest/install",
            "chmod +x /tmp/install_codedeploy",
            "/tmp/install_codedeploy auto",
            "systemctl enable codedeploy-agent",
            "systemctl start codedeploy-agent",

            # Tomcat を起動（WAR は CodeDeploy が配置するまで空の状態）
            "/opt/tomcat/bin/startup.sh",
        )

        # ============================================================
        # EC2 Instance
        # ============================================================
        self.instance = ec2.Instance(
            self, "EC2Instance",
            instance_name=f"{prefix}-ap-instance",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T2, ec2.InstanceSize.MICRO,
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=ec2_sg,
            role=ec2_role,
            key_pair=ec2.KeyPair.from_key_pair_name(self, "KeyPair", props.key_name),
            user_data=user_data,
        )

        # ============================================================
        # ALB
        # WAR デプロイ前は Tomcat が 404 を返すため healthy_http_codes に 404 を含める
        # ============================================================
        self.alb = elbv2.ApplicationLoadBalancer(
            self, "ALB",
            load_balancer_name=f"{prefix}-alb",
            vpc=self.vpc,
            internet_facing=True,
            security_group=alb_sg,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        listener = self.alb.add_listener("HTTPListener", port=80, open=False)
        listener.add_targets(
            "EC2Target",
            port=8080,
            targets=[targets.InstanceTarget(self.instance, 8080)],
            target_group_name=f"{prefix}-tg",
            health_check=elbv2.HealthCheck(
                path="/",
                port="8080",
                protocol=elbv2.Protocol.HTTP,
                healthy_http_codes="200-404",
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
            ),
        )

        # ============================================================
        # CodeDeploy
        # EC2 インスタンスへの WAR 自動デプロイを管理する
        # ============================================================
        self.deploy_application = codedeploy.ServerApplication(
            self, "DeployApplication",
            application_name=f"{prefix}-deploy-app",
        )

        self.deployment_group = codedeploy.ServerDeploymentGroup(
            self, "DeploymentGroup",
            application=self.deploy_application,
            deployment_group_name=f"{prefix}-deploy-group",
            # Name タグで EC2 インスタンスを特定する
            ec2_instance_tags=codedeploy.InstanceTagSet(
                {"Name": [f"{prefix}-ap-instance"]},
            ),
            # UserData でエージェントをインストール済みのため auto install は不要
            install_agent=False,
        )
