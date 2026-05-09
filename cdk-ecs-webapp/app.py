import aws_cdk as cdk
from pipeline.pipeline_stack import PipelineStack

app = cdk.App()

employee_id = app.node.try_get_context("employee_id") or "my"

PipelineStack(
    app,
    f"{employee_id}-EcsPipelineStack",
    env=cdk.Environment(region="ap-northeast-1"),
)

app.synth()
