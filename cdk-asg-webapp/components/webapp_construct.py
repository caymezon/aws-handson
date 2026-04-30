from dataclasses import dataclass, field
from aws_cdk import (
    Duration,
    RemovalPolicy,
    SecretValue,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
    aws_ssm as ssm,
    aws_s3 as s3,
    aws_codedeploy as codedeploy,
    aws_autoscaling as autoscaling,
)
from constructs import Construct


@dataclass
class WebappProps:
    """
    WebappConstruct に渡す設定値をまとめた Props クラス。
    cdk-webapp-pipeline との主な違い:
      - key_name / my_ip を削除（SSH → SSM Session Manager に変更）
      - asg_min / asg_max / asg_desired を追加
    """
    employee_id: str
    db_password: str
    tomcat_version: str = field(default="10.1.28")
    asg_min: int = field(default=1)
    asg_max: int = field(default=3)
    asg_desired: int = field(default=1)


class WebappConstruct(Construct):
    """
    ALB + Auto Scaling Group(Tomcat + Spring Boot) + RDS の3層Webアーキテクチャ。

    cdk-webapp-pipeline との主な違い:
      - 単一 EC2 Instance → Launch Template + Auto Scaling Group
      - CPU 使用率に応じてインスタンス数が自動スケール（ターゲット追跡: 60%）
      - SSH キーペア不要（SSM Session Manager で接続）
      - CodeDeploy が ASG を直接ターゲット指定
        → スケールアウト時に新インスタンスへ最新 WAR が自動デプロイされる
      - ALB ヘルスチェックを ASG ヘルスチェックにも連動

    --- 公開属性 ---
      self.alb              : ApplicationLoadBalancer
      self.asg              : AutoScalingGroup
      self.db_instance      : DatabaseInstance (RDS)
      self.vpc              : Vpc
      self.artifact_bucket  : Bucket (CodeDeploy デプロイバンドル置き場)
      self.deploy_application : ServerApplication (CodeDeploy)
      self.deployment_group   : ServerDeploymentGroup (CodeDeploy)
    """

    def __init__(self, scope: Construct, id: str, *, props: WebappProps) -> None:
        super().__init__(scope, id)

        prefix = f"{props.employee_id}-cdk5"

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

        # S3 VPC エンドポイント（ASG インスタンスが S3 からデプロイバンドルを取得するために使用）
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
            description=f"{prefix} ASG EC2 Tomcat SG",
        )
        # SSH は不要（SSM Session Manager で接続）
        ec2_sg.add_ingress_rule(alb_sg, ec2.Port.tcp(8080), "Tomcat from ALB SG only (SG-to-SG)")

        rds_sg = ec2.SecurityGroup(
            self, "RDSSecurityGroup",
            vpc=self.vpc,
            security_group_name=f"{prefix}-rds-sg",
            description=f"{prefix} RDS MySQL SG",
        )
        rds_sg.add_ingress_rule(ec2_sg, ec2.Port.tcp(3306), "MySQL from EC2 SG only (SG-to-SG)")

        # ============================================================
        # SSM Parameter Store（DBパスワードを安全に管理）
        # ============================================================
        ssm.StringParameter(
            self, "DBPasswordParam",
            parameter_name=f"/{props.employee_id}/cdk5/db-password",
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
        # IAM Role for EC2 (ASG インスタンス共通)
        # ============================================================
        ec2_role = iam.Role(
            self, "EC2Role",
            role_name=f"{prefix}-ec2-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                # SSM Session Manager でのブラウザ接続に必要
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                # UserData で SSM Parameter（DBパスワード）を取得するために必要
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMReadOnlyAccess"),
            ],
        )
        # CodeDeploy が S3 からデプロイバンドルを取得するために EC2 ロールに S3 読み取り権限を付与
        self.artifact_bucket.grant_read(ec2_role)

        # ============================================================
        # EC2 UserData（Launch Template に設定）
        # cdk-webapp-pipeline との違い:
        #   - stress-ng をインストール（スケーリング体験用）
        #   - CodeDeploy エージェント起動確認ループを追加
        #   - SSH キーペアなし
        # ============================================================
        rds_endpoint = self.db_instance.db_instance_endpoint_address

        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "set -xe",
            "exec > >(tee /var/log/user-data.log) 2>&1",

            # Java 17 + Tomcat + stress-ng（CPU負荷テスト用）インストール
            "dnf install -y java-17-amazon-corretto wget ruby stress-ng",
            "cd /opt",
            f"wget -q https://archive.apache.org/dist/tomcat/tomcat-10/v{props.tomcat_version}/bin/apache-tomcat-{props.tomcat_version}.tar.gz",
            f"tar xzf apache-tomcat-{props.tomcat_version}.tar.gz",
            f"mv apache-tomcat-{props.tomcat_version} tomcat",
            "chmod +x /opt/tomcat/bin/*.sh",

            # DB 接続情報を setenv.sh に書き込む
            # DB_HOST: CloudFormation が RDS エンドポイントを解決して埋め込む
            # DB_PASSWORD: 実行時に SSM Parameter Store から取得
            f"DB_PASSWORD=$(aws ssm get-parameter --name '/{props.employee_id}/cdk5/db-password' --query Parameter.Value --output text --region ap-northeast-1)",
            f"echo 'export DB_HOST={rds_endpoint}' > /opt/tomcat/bin/setenv.sh",
            'echo "export DB_PASSWORD=$DB_PASSWORD" >> /opt/tomcat/bin/setenv.sh',
            "chmod +x /opt/tomcat/bin/setenv.sh",

            # CodeDeploy エージェントをインストール
            "wget -O /tmp/install_codedeploy https://aws-codedeploy-ap-northeast-1.s3.ap-northeast-1.amazonaws.com/latest/install",
            "chmod +x /tmp/install_codedeploy",
            "/tmp/install_codedeploy auto",
            "systemctl enable codedeploy-agent",
            "systemctl start codedeploy-agent",

            # CodeDeploy エージェントの起動確認（ASG ライフサイクルフック対応）
            # スケールアウト時にエージェントが起動済みの状態でフックを受け取るために必要
            "for i in $(seq 1 12); do systemctl is-active codedeploy-agent && break || (echo \"Waiting for CodeDeploy agent... ($i/12)\" && sleep 10); done",

            # Tomcat を起動（WAR は後でパイプラインの CodeDeploy ステップが配置する）
            "/opt/tomcat/bin/startup.sh",
        )

        # ============================================================
        # Launch Template（ASG の起動設定）
        # cdk-webapp-pipeline の ec2.Instance に相当するが、ASG が複数インスタンスを管理する
        # ============================================================
        launch_template = ec2.LaunchTemplate(
            self, "LaunchTemplate",
            launch_template_name=f"{prefix}-lt",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T2, ec2.InstanceSize.MICRO,
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            security_group=ec2_sg,
            role=ec2_role,
            user_data=user_data,
        )

        # ============================================================
        # Auto Scaling Group（cdk-webapp-pipeline の単一 EC2 Instance を置き換え）
        # ============================================================
        self.asg = autoscaling.AutoScalingGroup(
            self, "ASG",
            auto_scaling_group_name=f"{prefix}-asg",
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            launch_template=launch_template,
            min_capacity=props.asg_min,
            max_capacity=props.asg_max,
            desired_capacity=props.asg_desired,
            # ALB ヘルスチェックの結果を ASG ヘルスチェックにも反映する
            # 5分間のグレースピリオド: UserData + CodeDeploy 完了を待つ
            health_check=autoscaling.HealthCheck.elb(
                grace=Duration.minutes(5),
            ),
        )

        # ターゲット追跡スケーリングポリシー
        # CPU 使用率が 60% を超えるとスケールアウト、下回るとスケールイン
        self.asg.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=60,
            cooldown=Duration.seconds(60),
            disable_scale_in=False,
        )

        # ============================================================
        # ALB
        # ============================================================
        self.alb = elbv2.ApplicationLoadBalancer(
            self, "ALB",
            load_balancer_name=f"{prefix}-alb",
            vpc=self.vpc,
            internet_facing=True,
            security_group=alb_sg,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        # HTTP リスナー（port 80）
        http_listener = self.alb.add_listener("HTTPListener", port=80, open=False)

        # ターゲットグループ（ASG をターゲットに登録）
        # WAR デプロイ前は Tomcat が 404 を返すため healthy_http_codes に 404 を含める
        http_listener.add_targets(
            "ASGTarget",
            port=8080,
            targets=[self.asg],
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
        # cdk-webapp-pipeline との主な違い:
        #   - ec2_instance_tags → auto_scaling_groups（ASG を直接指定）
        #   - ASG ライフサイクルフックが自動設定される
        #     → スケールアウト時に新インスタンスへ最新 WAR が自動デプロイされる
        # ============================================================
        self.deploy_application = codedeploy.ServerApplication(
            self, "DeployApplication",
            application_name=f"{prefix}-deploy-app",
        )

        self.deployment_group = codedeploy.ServerDeploymentGroup(
            self, "DeploymentGroup",
            application=self.deploy_application,
            deployment_group_name=f"{prefix}-deploy-group",
            # ASG を直接指定（cdk-webapp-pipeline の ec2_instance_tags タグ指定と異なる点）
            auto_scaling_groups=[self.asg],
            # UserData でエージェントをインストール済みのため auto install は不要
            install_agent=False,
            # ALL_AT_ONCE: 全インスタンスに同時デプロイ（シンプル・学習向け）
            deployment_config=codedeploy.ServerDeploymentConfig.ALL_AT_ONCE,
        )
