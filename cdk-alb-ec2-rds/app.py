import aws_cdk as cdk
from stacks.alb_ec2_rds_stack import AlbEc2RdsStack

app = cdk.App()

AlbEc2RdsStack(
    app,
    "CdkAlbEc2RdsStack",
    env=cdk.Environment(region="ap-northeast-1"),
)

app.synth()
