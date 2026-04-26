import aws_cdk as cdk
from constructs import Construct
from stacks.three_tier_stack import ThreeTierStack


class ThreeTierStage(cdk.Stage):
    """
    CDK Pipelines の Stage クラス。

    Stage はデプロイ単位をまとめるコンテナ。
    複数スタックを1つの Stage にまとめると、パイプラインが順序制御してデプロイする。
    このハンズオンでは ThreeTierStack 1つだけを内包する。
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ThreeTierStack(self, "ThreeTierStack")
