import aws_cdk as cdk
from aws_cdk import Stack, aws_iam as iam, aws_codebuild as codebuild
from aws_cdk.pipelines import CodePipeline, CodeBuildStep, CodePipelineSource
from constructs import Construct
from stages.webapp_stage import WebappStage


class PipelineStack(Stack):
    """
    CDK Pipelines で Spring Boot Webアプリの CI/CD パイプラインを定義するスタック。

    パイプラインの流れ:
      [Source]        GitHub からコードを取得
      [Synth]         CodeBuild で cdk synth → Cloud Assembly 生成
      [Mutate]        パイプライン自己更新（セルフミューテーション）
      [InfraDeploy]   CloudFormation → VPC / EC2 / RDS / ALB / CodeDeploy 設定
      [BuildAndDeployApp] ← post step
        1. CodeBuild: mvn package → webapp.war 生成
        2. CodeBuild: deployment.zip を S3 にアップロード
        3. CodeDeploy: EC2/Tomcat に WAR をホットデプロイ
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        employee_id    = self.node.try_get_context("employee_id")    or "my"
        github_owner   = self.node.try_get_context("github_owner")
        github_repo    = self.node.try_get_context("github_repo")
        github_branch  = self.node.try_get_context("github_branch")  or "main"
        connection_arn = self.node.try_get_context("connection_arn")
        prefix = f"{employee_id}-cdk4"

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
                    "cd cdk-webapp-pipeline",
                    "pip install -r requirements.txt",
                    "npx cdk synth",
                ],
                primary_output_directory="cdk-webapp-pipeline/cdk.out",
            ),
            cross_account_keys=False,
        )

        # ── Deploy Stage ─────────────────────────────────────────────
        # ステージ名に employee_id を含めることで、同一 AWS アカウントで複数人が
        # 実施してもスタック名が衝突しない（{id}-Deploy-WebappStack）
        stage = WebappStage(
            self, f"{employee_id}-Deploy",
            env=cdk.Environment(region="ap-northeast-1"),
        )

        # ── Post Step: Maven ビルド → S3 → CodeDeploy ────────────────
        # インフラデプロイ完了後に実行される。
        # env_from_cfn_outputs で WebappStack の CfnOutput を環境変数として受け取る。
        build_and_deploy = CodeBuildStep(
            "BuildAndDeployApp",
            input=source,
            env_from_cfn_outputs={
                "ARTIFACT_BUCKET":  stage.artifact_bucket_output,
                "DEPLOY_APP_NAME":  stage.deploy_app_name_output,
                "DEPLOY_GROUP_NAME": stage.deploy_group_name_output,
                "INSTANCE_ID":      stage.instance_id_output,
            },
            build_environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
            ),
            # CodeDeploy / S3 / EC2 操作に必要な IAM 権限
            role_policy_statements=[
                iam.PolicyStatement(
                    actions=[
                        "codedeploy:CreateDeployment",
                        "codedeploy:GetDeployment",
                        "codedeploy:GetDeploymentConfig",
                        "codedeploy:RegisterApplicationRevision",
                        "codedeploy:GetApplicationRevision",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    actions=["s3:PutObject", "s3:GetObject"],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    actions=["ec2:DescribeInstanceStatus"],
                    resources=["*"],
                ),
            ],
            commands=[
                # ─── 1. Maven で WAR をビルド ───────────────────────
                "echo '=== Building Spring Boot WAR ==='",
                "cd cdk-webapp-pipeline/app",
                "mvn package -DskipTests",
                "cd ../..",

                # ─── 2. CodeDeploy デプロイバンドルを作成 ──────────
                # bundle/: appspec.yml + webapp.war + scripts/
                "echo '=== Creating deployment bundle ==='",
                "rm -rf deploy_bundle && mkdir deploy_bundle",
                "cp cdk-webapp-pipeline/appspec.yml deploy_bundle/",
                "cp cdk-webapp-pipeline/app/target/webapp.war deploy_bundle/",
                "cp -r cdk-webapp-pipeline/scripts/ deploy_bundle/scripts/",
                "cd deploy_bundle && zip -r ../deployment.zip . && cd ..",

                # ─── 3. S3 にアップロード ───────────────────────────
                "echo '=== Uploading bundle to S3 ==='",
                "aws s3 cp deployment.zip s3://$ARTIFACT_BUCKET/deployment.zip",

                # ─── 4. EC2 の起動完了を待つ ────────────────────────
                # UserData（Tomcat + CodeDeploy エージェント起動）が完了するまで待機
                "echo \"=== Waiting for EC2 ($INSTANCE_ID) to pass health checks ===\"",
                "aws ec2 wait instance-status-ok --instance-ids $INSTANCE_ID",
                "echo '=== EC2 is ready. Waiting 30s for CodeDeploy agent to start ==='",
                "sleep 30",

                # ─── 5. CodeDeploy でデプロイ実行 ───────────────────
                "echo '=== Triggering CodeDeploy deployment ==='",
                "DEPLOY_ID=$(aws deploy create-deployment --application-name $DEPLOY_APP_NAME --deployment-group-name $DEPLOY_GROUP_NAME --s3-location bucket=$ARTIFACT_BUCKET,bundleType=zip,key=deployment.zip --query deploymentId --output text)",
                "echo \"CodeDeploy Deployment ID: $DEPLOY_ID\"",
                "aws deploy wait deployment-successful --deployment-id $DEPLOY_ID",
                "echo '=== Application deployment complete! ==='",
            ],
        )

        pipeline.add_stage(stage, post=[build_and_deploy])
