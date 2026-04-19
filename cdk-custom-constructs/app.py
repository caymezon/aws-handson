import aws_cdk as cdk
from stacks.three_tier_stack import ThreeTierStack

app = cdk.App()

# 単一環境デプロイ
# 同じ ThreeTierStack を複数インスタンス化すれば dev/prod の並列デプロイも可能:
#   ThreeTierStack(app, "ThreeTierDevStack",  env=..., ← cdk.json の context "employee_id" を dev 用に切り替え)
#   ThreeTierStack(app, "ThreeTierProdStack", env=..., ← prod 用に切り替え)
ThreeTierStack(
    app,
    "CdkCustomConstructsStack",
    env=cdk.Environment(region="ap-northeast-1"),
)

app.synth()
