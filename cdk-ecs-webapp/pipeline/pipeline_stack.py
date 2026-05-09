import aws_cdk as cdk
from aws_cdk import Stack
from aws_cdk.pipelines import CodePipeline, CodePipelineSource, CodeBuildStep
# BuildAndDeployApp を有効にする場合は以下のインポートも追加:
# from aws_cdk import aws_iam as iam, aws_codebuild as codebuild
from constructs import Construct
from stages.deploy_stage import WebappStage


class PipelineStack(Stack):
    """
    CDK Pipelines で ECS Fargate Webアプリの CI/CD パイプラインを定義するスタック。

    【現在の構成】インフラとアプリのデプロイを分離
      [Source]        GitHub からコードを取得
      [Synth]         CodeBuild で cdk synth → Cloud Assembly 生成
      [Mutate]        パイプライン自己更新（セルフミューテーション）
      [InfraDeploy]   CloudFormation → VPC / ECR / ECS / RDS / ALB
        ※ アプリのデプロイは GitHub Actions（.github/workflows/ecs-app-deploy.yml）が担当

    【補足】BuildAndDeployApp について:
      CDK Pipelines にアプリデプロイを含める構成も可能（下部にコメントアウトで残してある）。
      その場合は CDK Pipelines のみで完結するが、以下の問題がある:
        - アプリのみの変更でも全ステージが走り 10〜15 分かかる
        - GitHub Actions と組み合わせると同じ ECS サービスに二重デプロイが発生する
      実務ではインフラとアプリのデプロイを分離するのが一般的。
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        employee_id    = self.node.try_get_context("employee_id")    or "my"
        github_owner   = self.node.try_get_context("github_owner")
        github_repo    = self.node.try_get_context("github_repo")
        github_branch  = self.node.try_get_context("github_branch")  or "main"
        connection_arn = self.node.try_get_context("connection_arn")
        prefix = f"{employee_id}-cdk6"

        # ── Source: GitHub ───────────────────────────────────────────
        source = CodePipelineSource.connection(
            f"{github_owner}/{github_repo}",
            github_branch,
            connection_arn=connection_arn,
        )

        # ── Pipeline ─────────────────────────────────────────────────
        pipeline = CodePipeline(
            self, "Pipeline",
            pipeline_name=f"{prefix}-pipeline",
            synth=CodeBuildStep(
                "Synth",
                input=source,
                commands=[
                    "cd cdk-ecs-webapp",
                    "pip install -r requirements.txt",
                    "npx cdk synth",
                ],
                primary_output_directory="cdk-ecs-webapp/cdk.out",
            ),
            cross_account_keys=False,
        )

        # ── Deploy Stage（インフラのみ）────────────────────────────────
        stage = WebappStage(
            self, f"{employee_id}-Deploy",
            env=cdk.Environment(region="ap-northeast-1"),
        )

        pipeline.add_stage(stage)
        # BuildAndDeployApp を有効にする場合は上の行を以下に変更:
        # pipeline.add_stage(stage, post=[build_and_deploy])

        # ============================================================
        # 【補足】BuildAndDeployApp（CDK Pipelines でアプリもデプロイする構成）
        #
        # アプリデプロイを CDK Pipelines に含める場合はコメントを外して使用する。
        # インフラデプロイ完了後に実行される。
        # env_from_cfn_outputs で WebappStack の CfnOutput を環境変数として受け取る。
        #
        # ※ この構成を使う場合は上部の import コメントも外すこと。
        # ============================================================
        # build_and_deploy = CodeBuildStep(
        #     "BuildAndDeployApp",
        #     input=source,
        #     env_from_cfn_outputs={
        #         "ECR_REPO_URI":    stage.ecr_repo_uri_output,
        #         "ECS_CLUSTER_NAME": stage.cluster_name_output,
        #         "ECS_SERVICE_NAME": stage.service_name_output,
        #         "TASK_DEF_FAMILY": stage.task_def_family_output,
        #         "CONTAINER_NAME":  stage.container_name_output,
        #     },
        #     build_environment=codebuild.BuildEnvironment(
        #         build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
        #         privileged=True,
        #     ),
        #     role_policy_statements=[
        #         iam.PolicyStatement(
        #             actions=["ecr:GetAuthorizationToken"],
        #             resources=["*"],
        #         ),
        #         iam.PolicyStatement(
        #             actions=[
        #                 "ecr:BatchCheckLayerAvailability",
        #                 "ecr:PutImage",
        #                 "ecr:InitiateLayerUpload",
        #                 "ecr:UploadLayerPart",
        #                 "ecr:CompleteLayerUpload",
        #             ],
        #             resources=["*"],
        #         ),
        #         iam.PolicyStatement(
        #             actions=[
        #                 "ecs:DescribeTaskDefinition",
        #                 "ecs:RegisterTaskDefinition",
        #                 "ecs:UpdateService",
        #                 "ecs:DescribeServices",
        #             ],
        #             resources=["*"],
        #         ),
        #         iam.PolicyStatement(
        #             actions=["iam:PassRole"],
        #             resources=["*"],
        #         ),
        #     ],
        #     commands=[
        #         "echo '=== Building Docker image ==='",
        #         "cd cdk-ecs-webapp && docker build -t webapp:build . && cd ..",
        #         "echo '=== Pushing to ECR ==='",
        #         "aws ecr get-login-password --region ap-northeast-1 | docker login --username AWS --password-stdin $ECR_REPO_URI",
        #         "docker tag webapp:build $ECR_REPO_URI:latest",
        #         "docker push $ECR_REPO_URI:latest",
        #         "echo '=== Registering new task definition ==='",
        #         "aws ecs describe-task-definition --task-definition $TASK_DEF_FAMILY --query taskDefinition --region ap-northeast-1 > /tmp/td.json",
        #         "python3 -c \"import json,os; td=json.load(open('/tmp/td.json')); [td.pop(k,None) for k in ['taskDefinitionArn','revision','status','requiresAttributes','compatibilities','registeredAt','registeredBy']]; [c.update({'image':os.environ['ECR_REPO_URI']+':latest'}) for c in td['containerDefinitions'] if c['name']==os.environ['CONTAINER_NAME']]; json.dump(td,open('/tmp/new_td.json','w'))\"",
        #         "NEW_TASK_DEF_ARN=$(aws ecs register-task-definition --cli-input-json file:///tmp/new_td.json --region ap-northeast-1 --query taskDefinition.taskDefinitionArn --output text)",
        #         "echo \"New task definition: $NEW_TASK_DEF_ARN\"",
        #         "echo '=== Updating ECS service ==='",
        #         "aws ecs update-service --cluster $ECS_CLUSTER_NAME --service $ECS_SERVICE_NAME --task-definition $NEW_TASK_DEF_ARN --region ap-northeast-1",
        #         "echo '=== Waiting for ECS service to stabilize ==='",
        #         "python3 -c \"import boto3,time,sys,os; ecs=boto3.client('ecs',region_name='ap-northeast-1'); cl=os.environ['ECS_CLUSTER_NAME']; sv=os.environ['ECS_SERVICE_NAME']; [print('Service is stable!') or sys.exit(0) if (s:=ecs.describe_services(cluster=cl,services=[sv])['services'][0]) and len(s['deployments'])==1 and s['runningCount']==s['desiredCount'] else print('  Wait {}/{}: deployments={} running={}/{}'.format(i+1,60,len(s['deployments']),s['runningCount'],s['desiredCount'])) or time.sleep(15) for i in range(60)]; print('ERROR: Service did not stabilize within 15 minutes'); sys.exit(1)\"",
        #         "echo '=== Deployment complete! ==='",
        #     ],
        # )
