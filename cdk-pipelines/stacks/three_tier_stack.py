from aws_cdk import Stack, CfnOutput
from constructs import Construct
from components.three_tier_web import ThreeTierWebConstruct, ThreeTierWebProps


class ThreeTierStack(Stack):
    """
    ThreeTierWebConstruct を使って 3層Web構成をデプロイするスタック。

    cdk-custom-constructs の ThreeTierStack と同じ構造。
    CDK Pipelines では Stage の中にこのスタックを配置することで、
    パイプラインが自動的にデプロイを実行する。
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        employee_id = self.node.try_get_context("employee_id") or "my"
        props = ThreeTierWebProps(
            employee_id=employee_id,
            my_ip=self.node.try_get_context("my_ip") or "0.0.0.0/0",
            db_password=self.node.try_get_context("db_password") or "Handson1234!",
            key_name=self.node.try_get_context("key_name") or f"n{employee_id}-cdk3-key",
            tomcat_version=self.node.try_get_context("tomcat_version") or "10.1.28",
        )

        web = ThreeTierWebConstruct(self, "Web", props=props)

        CfnOutput(self, "ALBEndpoint",
            description="ALB DNS name - access via browser",
            value=f"http://{web.alb.load_balancer_dns_name}",
        )
        CfnOutput(self, "EC2PublicIP",
            description="EC2 Tomcat server public IP (for SSH)",
            value=web.instance.instance_public_ip,
        )
        CfnOutput(self, "RDSEndpoint",
            description="RDS MySQL endpoint hostname",
            value=web.db_instance.db_instance_endpoint_address,
        )
        CfnOutput(self, "SSHCommand",
            description="SSH command to EC2 AP server",
            value=f"ssh -i %USERPROFILE%\\.ssh\\{props.key_name}.pem ec2-user@{web.instance.instance_public_ip}",
        )
        CfnOutput(self, "MySQLConnectCommand",
            description="MySQL connect command (run FROM the EC2 AP server)",
            value=f"mysql -h {web.db_instance.db_instance_endpoint_address} -u admin -p{props.db_password} sampledb",
        )
