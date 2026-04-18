from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    SecretValue,
    CfnOutput,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_targets as targets,
    aws_iam as iam,
    aws_ssm as ssm,
)
from constructs import Construct


class AlbEc2RdsStack(Stack):
    """
    ALB + EC2(Tomcat) + RDS 3層構成を CDK (Python) で実装したスタック。
    CloudFormation 版（alb-ec2-rds/template.yaml）と同等のインフラを構築する。

    CDK の主な利点:
    - VPC: L2 Construct 1つで IGW・ルートテーブル・サブネットを自動生成（CloudFormation では 15+ リソース）
    - SG-to-SG 制御: add_ingress_rule(sg, ...) で直感的に記述
    - ALB → リスナー → ターゲットグループ: メソッドチェーンで接続関係が明確
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ============================================================
        # Context 変数（cdk.json または -c フラグで上書き可能）
        # ============================================================
        employee_id    = self.node.try_get_context("employee_id")   or "my"
        my_ip          = self.node.try_get_context("my_ip")         or "0.0.0.0/0"
        db_password    = self.node.try_get_context("db_password")   or "Handson1234!"
        key_name       = self.node.try_get_context("key_name")      or f"n{employee_id}-cdk-alb-key"
        tomcat_version = self.node.try_get_context("tomcat_version") or "10.1.28"

        prefix = f"n{employee_id}-cdk"

        # ============================================================
        # VPC
        # CDK L2 Construct が以下を自動生成:
        #   - IGW・VPCGatewayAttachment
        #   - パブリック/プライベート サブネット（各 2AZ）
        #   - ルートテーブル・サブネットアソシエーション
        #   - パブリックサブネットのデフォルトルート (0.0.0.0/0 → IGW)
        # CloudFormation 版と同等のリソースを ~1/10 の記述量で実現
        # ============================================================
        vpc = ec2.Vpc(
            self, "VPC",
            vpc_name=f"{prefix}-alb-vpc",
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

        # S3 VPC Gateway Endpoint（無料）: EC2 から S3 への通信を VPC 内で完結させる
        vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )

        # ============================================================
        # Security Groups
        # add_ingress_rule(sg_object, ...) で SG-to-SG 制御を直感的に記述
        # ============================================================

        # ALB SG: インターネットから HTTP:80 を受け付ける
        alb_sg = ec2.SecurityGroup(
            self, "ALBSecurityGroup",
            vpc=vpc,
            security_group_name=f"{prefix}-alb-sg",
            description=f"{prefix} ALB SG - HTTP:80 from internet",
        )
        alb_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(80),
            "HTTP from internet",
        )

        # EC2 SG: Tomcat:8080 は ALB SG からのみ / SSH は自分のIPのみ
        ec2_sg = ec2.SecurityGroup(
            self, "EC2SecurityGroup",
            vpc=vpc,
            security_group_name=f"{prefix}-ec2-sg",
            description=f"{prefix} EC2 Tomcat SG",
        )
        ec2_sg.add_ingress_rule(alb_sg, ec2.Port.tcp(8080), "Tomcat from ALB SG only (SG-to-SG)")
        ec2_sg.add_ingress_rule(ec2.Peer.ipv4(my_ip), ec2.Port.tcp(22), "SSH from my IP")

        # RDS SG: MySQL:3306 は EC2 SG からのみ
        rds_sg = ec2.SecurityGroup(
            self, "RDSSecurityGroup",
            vpc=vpc,
            security_group_name=f"{prefix}-rds-sg",
            description=f"{prefix} RDS MySQL SG",
        )
        rds_sg.add_ingress_rule(ec2_sg, ec2.Port.tcp(3306), "MySQL from EC2 SG only (SG-to-SG)")

        # ============================================================
        # SSM Parameter Store（DBパスワードを保存）
        # ============================================================
        ssm.StringParameter(
            self, "DBPasswordParam",
            parameter_name=f"/n{employee_id}/cdk-alb/db-password",
            string_value=db_password,
            description=f"RDS MySQL master password for {prefix} ALB hands-on",
        )

        # ============================================================
        # RDS MySQL
        # DatabaseInstance L2 Construct が以下を自動生成:
        #   - DBSubnetGroup（2AZ 要件を自動満足）
        #   - DB パラメータグループ（デフォルト）
        # ============================================================
        db_instance = rds.DatabaseInstance(
            self, "RDSInstance",
            database_name="sampledb",
            engine=rds.DatabaseInstanceEngine.mysql(
                version=rds.MysqlEngineVersion.VER_8_0,
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.MICRO,
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
            ),
            security_groups=[rds_sg],
            credentials=rds.Credentials.from_username(
                "admin",
                password=SecretValue.unsafe_plain_text(db_password),
            ),
            instance_identifier=f"{prefix}-alb-rds-mysql",
            multi_az=False,
            publicly_accessible=False,
            allocated_storage=20,
            backup_retention=Duration.days(0),
            delete_automated_backups=True,
            deletion_protection=False,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ============================================================
        # IAM Role for EC2（SSM Parameter Store の読み取りを許可）
        # ============================================================
        ec2_role = iam.Role(
            self, "EC2Role",
            role_name=f"{prefix}-alb-ec2-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMReadOnlyAccess"),
            ],
        )

        # ============================================================
        # EC2 UserData（Tomcat のインストールと起動）
        # CDK では f-string で変数を直接埋め込める（CloudFormation の ${!VAR} 不要）
        # ============================================================
        html_content = (
            "cat > /opt/tomcat/webapps/ROOT/index.html << 'HTMLEOF'\n"
            "<!DOCTYPE html>\n"
            "<html><body>\n"
            f"<h1>AP Server - {prefix} ALB + EC2 + RDS</h1>\n"
            "<p>Deployed via AWS CDK (Python). Connects to RDS MySQL in the private subnet.</p>\n"
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
            "/opt/tomcat/bin/startup.sh",
        )

        # ============================================================
        # EC2 Instance（Tomcat AP サーバ）
        # ============================================================
        instance = ec2.Instance(
            self, "EC2Instance",
            instance_name=f"{prefix}-alb-ap-instance",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T2, ec2.InstanceSize.MICRO,
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=ec2_sg,
            role=ec2_role,
            key_pair=ec2.KeyPair.from_key_pair_name(self, "KeyPair", key_name),
            user_data=user_data,
        )

        # ============================================================
        # ALB（Application Load Balancer）
        # add_listener → add_targets でリスナー・TG・ヘルスチェックを一気に設定
        # CloudFormation 版では ALB・Listener・TargetGroup を別々に定義が必要
        # ============================================================
        alb = elbv2.ApplicationLoadBalancer(
            self, "ALB",
            load_balancer_name=f"{prefix}-alb-alb",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_sg,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        listener = alb.add_listener(
            "HTTPListener",
            port=80,
            open=False,
        )

        listener.add_targets(
            "EC2Target",
            port=8080,
            targets=[targets.InstanceTarget(instance, 8080)],
            target_group_name=f"{prefix}-alb-tg",
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

        # ============================================================
        # Outputs
        # ============================================================
        CfnOutput(self, "ALBEndpoint",
            description="ALB DNS name - access via browser",
            value=f"http://{alb.load_balancer_dns_name}",
        )
        CfnOutput(self, "EC2PublicIP",
            description="EC2 Tomcat server public IP (for SSH)",
            value=instance.instance_public_ip,
        )
        CfnOutput(self, "RDSEndpoint",
            description="RDS MySQL endpoint hostname",
            value=db_instance.db_instance_endpoint_address,
        )
        CfnOutput(self, "SSHCommand",
            description="SSH command to EC2 AP server",
            value=f"ssh -i ~/.ssh/{key_name}.pem ec2-user@{instance.instance_public_ip}",
        )
        CfnOutput(self, "MySQLConnectCommand",
            description="MySQL connect command (run FROM the EC2 AP server)",
            value=f"mysql -h {db_instance.db_instance_endpoint_address} -u admin -p{db_password} sampledb",
        )
