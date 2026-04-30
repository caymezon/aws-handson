from aws_cdk import Stack, CfnOutput
from constructs import Construct
from components.webapp_construct import WebappConstruct, WebappProps


class WebappStack(Stack):
    """
    WebappConstruct を使って ASG ベースの3層WebアプリをデプロイするCDKスタック。

    このスタックはパイプラインの InfraDeploy ステージで CloudFormation によってデプロイされる。
    後続の BuildAndDeployApp ステップ（CodeDeploy）が参照するリソース名を
    CfnOutput で公開する。

    cdk-webapp-pipeline との違い:
      - instance_id_output を廃止し asg_name_output を追加
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        employee_id = self.node.try_get_context("employee_id") or "my"
        props = WebappProps(
            employee_id=employee_id,
            db_password=self.node.try_get_context("db_password") or "Handson1234!",
            tomcat_version=self.node.try_get_context("tomcat_version") or "10.1.28",
            asg_min=int(self.node.try_get_context("asg_min_capacity") or 1),
            asg_max=int(self.node.try_get_context("asg_max_capacity") or 3),
            asg_desired=int(self.node.try_get_context("asg_desired_capacity") or 1),
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
        # cdk-webapp-pipeline の InstanceId の代わりに ASGName を出力
        # パイプラインがインスタンス起動完了を確認するために使用
        self.asg_name_output = CfnOutput(
            self, "ASGName",
            description="Auto Scaling Group name (used to wait for instances to be InService)",
            value=web.asg.auto_scaling_group_name,
        )

        # ── User-facing Outputs ──────────────────────────────────────
        CfnOutput(self, "ALBEndpoint",
            description="ALB DNS name - access via browser (available after CodeDeploy completes)",
            value=f"http://{web.alb.load_balancer_dns_name}",
        )
        CfnOutput(self, "RDSEndpoint",
            description="RDS MySQL endpoint hostname",
            value=web.db_instance.db_instance_endpoint_address,
        )
