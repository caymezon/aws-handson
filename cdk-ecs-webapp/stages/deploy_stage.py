import aws_cdk as cdk
from constructs import Construct
from stacks.webapp_stack import WebappStack


class WebappStage(cdk.Stage):
    """
    CDK Pipelines の Stage クラス。

    WebappStack（インフラ + ECS 設定）を内包する。
    パイプラインの後続ステップ（BuildAndDeployApp）が参照するスタック出力を
    プロパティとして公開する。

    cdk-asg-webapp との違い:
      - artifact_bucket / deploy_app_name / deploy_group_name / asg_name を廃止
      - ecr_repo_uri / cluster_name / service_name / task_def_family / container_name を追加
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        stack = WebappStack(self, "WebappStack")

        # パイプラインの post ステップから env_from_cfn_outputs で参照される
        self.ecr_repo_uri_output    = stack.ecr_repo_uri_output
        self.cluster_name_output    = stack.cluster_name_output
        self.service_name_output    = stack.service_name_output
        self.task_def_family_output = stack.task_def_family_output
        self.container_name_output  = stack.container_name_output
