from aws_cdk import Stack, CfnOutput
from constructs import Construct
from components.webapp_construct import WebappConstruct, WebappProps


class WebappStack(Stack):
    """
    WebappConstruct を使って ECS Fargate ベースの3層WebアプリをデプロイするCDKスタック。

    このスタックはパイプラインの InfraDeploy ステージで CloudFormation によってデプロイされる。
    後続の BuildAndDeployApp ステップ（Docker build + ECR push + ECS update）が参照する
    リソース情報を CfnOutput で公開する。

    cdk-asg-webapp との違い:
      - ArtifactBucket / DeployApplicationName / DeployGroupName / ASGName を廃止
      - ECRRepoUri / ECSClusterName / ECSServiceName / TaskDefFamily / ContainerName を追加
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        employee_id = self.node.try_get_context("employee_id") or "my"
        props = WebappProps(
            employee_id=employee_id,
            db_password=self.node.try_get_context("db_password") or "Handson1234!",
            task_cpu=int(self.node.try_get_context("task_cpu") or 256),
            task_memory=int(self.node.try_get_context("task_memory") or 512),
            desired_count=int(self.node.try_get_context("desired_count") or 1),
        )

        web = WebappConstruct(self, "Web", props=props)

        # ── Outputs for pipeline post-step (BuildAndDeployApp) ───────
        # Docker build / ECR push / ECS update に必要な情報
        self.ecr_repo_uri_output = CfnOutput(
            self, "ECRRepoUri",
            description="ECR repository URI for Docker image push",
            value=web.ecr_repository.repository_uri,
        )
        self.cluster_name_output = CfnOutput(
            self, "ECSClusterName",
            description="ECS Cluster name",
            value=web.cluster.cluster_name,
        )
        self.service_name_output = CfnOutput(
            self, "ECSServiceName",
            description="ECS Service name",
            value=web.ecs_service.service_name,
        )
        # タスク定義ファミリー名: 現在のタスク定義を取得してイメージを更新するために使用
        self.task_def_family_output = CfnOutput(
            self, "TaskDefFamily",
            description="ECS Task Definition family name",
            value=web.task_def_family,
        )
        # コンテナ名: 複数コンテナ構成に備えて、更新対象のコンテナを特定するために使用
        self.container_name_output = CfnOutput(
            self, "ContainerName",
            description="Container name to update with new ECR image",
            value=web.container_name,
        )

        # ── User-facing Outputs ──────────────────────────────────────
        CfnOutput(self, "ALBEndpoint",
            description="ALB DNS name - access via browser (available after BuildAndDeployApp completes)",
            value=f"http://{web.alb.load_balancer_dns_name}",
        )
        CfnOutput(self, "RDSEndpoint",
            description="RDS MySQL endpoint hostname",
            value=web.db_instance.db_instance_endpoint_address,
        )
