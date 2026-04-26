import aws_cdk as cdk
from pipeline.pipeline_stack import PipelineStack

app = cdk.App()

PipelineStack(
    app,
    "CdkPipelinesStack",
    env=cdk.Environment(region="ap-northeast-1"),
)

app.synth()
