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
)
from constructs import Construct


@dataclass
class ThreeTierWebProps:
    """
    ThreeTierWebConstruct に渡す設定値をまとめた Props クラス。

    CDK では Construct の設定を Props（プロパティ）としてまとめるのが慣習。
    dataclass を使うことで型ヒントと省略時のデフォルト値を明示できる。
    """
    employee_id: str
    my_ip: str
    db_password: str
    key_name: str
    tomcat_version: str = field(default="10.1.28")


class ThreeTierWebConstruct(Construct):
    """
    ALB + EC2(Tomcat) + RDS の3層Webアーキテクチャをカプセル化したカスタム Construct。

    cdk-custom-constructs の ThreeTierWebConstruct と同じ定義。
    cdk-pipelines では CDK Pipelines がこの Construct を含むスタックを
    GitHub プッシュのたびに自動デプロイする。

    --- 公開属性（スタックから参照できる値） ---
      self.alb           : ApplicationLoadBalancer
      self.instance      : Instance (EC2)
      self.db_instance   : DatabaseInstance (RDS)
      self.vpc           : Vpc
    """

    def __init__(self, scope: Construct, id: str, *, props: ThreeTierWebProps) -> None:
        super().__init__(scope, id)

        prefix = f"n{props.employee_id}-cdk3"

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
            parameter_name=f"/n{props.employee_id}/cdk3/db-password",
            string_value=props.db_password,
            description=f"RDS MySQL master password for {prefix}",
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

        # ============================================================
        # EC2 UserData
        # ============================================================
        tomcat_version = props.tomcat_version
        html_content = (
            "cat > /opt/tomcat/webapps/ROOT/index.html << 'HTMLEOF'\n"
            "<!DOCTYPE html>\n"
            "<html><body>\n"
            f"<h1>AP Server - {prefix} 3-Tier Web</h1>\n"
            "<p>Deployed via AWS CDK Pipelines (auto-deployed on git push).</p>\n"
            "</body></html>\n"
            "HTMLEOF"
        )

        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "set -xe",
            "exec > >(tee /var/log/user-data.log) 2>&1",
            "dnf update -y",
            "dnf install -y java-17-amazon-corretto wget",
            "cd /opt",
            f"wget -q https://archive.apache.org/dist/tomcat/tomcat-10/v{tomcat_version}/bin/apache-tomcat-{tomcat_version}.tar.gz",
            f"tar xzf apache-tomcat-{tomcat_version}.tar.gz",
            f"mv apache-tomcat-{tomcat_version} tomcat",
            "chmod +x /opt/tomcat/bin/*.sh",
            "rm -rf /opt/tomcat/webapps/ROOT",
            "mkdir -p /opt/tomcat/webapps/ROOT",
            html_content,
            "cat > /etc/systemd/system/tomcat.service << 'EOF'\n[Unit]\nDescription=Apache Tomcat\nAfter=network.target\n\n[Service]\nType=forking\nExecStart=/opt/tomcat/bin/startup.sh\nExecStop=/opt/tomcat/bin/shutdown.sh\nUser=root\nGroup=root\nRestart=on-failure\nRestartSec=10\n\n[Install]\nWantedBy=multi-user.target\nEOF",
            "systemctl daemon-reload",
            "systemctl enable tomcat",
            "systemctl start tomcat",
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
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
            ),
        )
