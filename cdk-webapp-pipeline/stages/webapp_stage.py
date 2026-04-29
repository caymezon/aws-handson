import aws_cdk as cdk
from aws_cdk import CfnOutput
from constructs import Construct
from stacks.webapp_stack import WebappStack


class WebappStage(cdk.Stage):
    """
    CDK Pipelines の Stage クラス。

    WebappStack（インフラ + CodeDeploy 設定）を内包する。
    パイプラインの後続ステップ（BuildAndDeployApp）が参照するスタック出力を
    プロパティとして公開する。
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        stack = WebappStack(self, "WebappStack")

        # パイプラインの post ステップから env_from_cfn_outputs で参照される
        self.artifact_bucket_output = stack.artifact_bucket_output
        self.deploy_app_name_output  = stack.deploy_app_name_output
        self.deploy_group_name_output = stack.deploy_group_name_output
        self.instance_id_output      = stack.instance_id_output
