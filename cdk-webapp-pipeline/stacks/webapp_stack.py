from aws_cdk import Stack, CfnOutput
from constructs import Construct
from components.webapp_construct import WebappConstruct, WebappProps


class WebappStack(Stack):
    """
    WebappConstruct を使って 3層WebアプリをデプロイするCDKスタック。

    このスタックはパイプラインの InfraDeploy ステージで CloudFormation によってデプロイされる。
    後続の BuildAndDeployApp ステップ（CodeDeploy）が参照するリソース名を
    CfnOutput で公開する。
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        employee_id = self.node.try_get_context("employee_id") or "my"
        props = WebappProps(
            employee_id=employee_id,
            my_ip=self.node.try_get_context("my_ip") or "0.0.0.0/0",
            db_password=self.node.try_get_context("db_password") or "Handson1234!",
            key_name=self.node.try_get_context("key_name") or f"{employee_id}-cdk4-key",
            tomcat_version=self.node.try_get_context("tomcat_version") or "10.1.28",
        )

        web = WebappConstruct(self, "Web", props=props)

        # ── Outputs for pipeline post-step (BuildAndDeployApp) ───────
        # パイプラインの CodeDeploy ステップがこれらの値を env として受け取る
        self.artifact_bucket_output = CfnOutput(
            self, "ArtifactBucketName",
            description="S3 bucket for CodeDeploy deployment bundle",
            value=web.artifact_bucket.bucket_name,
        )
        self.deploy_app_name_output = CfnOutput(
            self, "DeployApplicationName",
            description="CodeDeploy application name",
            value=web.deploy_application.application_name,
        )
        self.deploy_group_name_output = CfnOutput(
            self, "DeployGroupName",
            description="CodeDeploy deployment group name",
            value=web.deployment_group.deployment_group_name,
        )
        self.instance_id_output = CfnOutput(
            self, "InstanceId",
            description="EC2 instance ID (used to wait for instance-status-ok)",
            value=web.instance.instance_id,
        )

        # ── User-facing Outputs ──────────────────────────────────────
        CfnOutput(self, "ALBEndpoint",
            description="ALB DNS name - access via browser (available after CodeDeploy completes)",
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
