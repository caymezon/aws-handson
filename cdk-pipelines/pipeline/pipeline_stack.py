import aws_cdk as cdk
from aws_cdk import Stack
from aws_cdk.pipelines import CodePipeline, CodeBuildStep, CodePipelineSource
from constructs import Construct
from stages.three_tier_stage import ThreeTierStage


class PipelineStack(Stack):
    """
    CDK Pipelines を使って CI/CD パイプラインを定義するスタック。

    このスタックをデプロイすると CodePipeline が作成され、
    GitHub へのプッシュを検知して自動的に 3層Web構成をデプロイする。

    パイプラインは「セルフミューテーション（自己更新）」対応:
      - パイプライン自身のコードを変更してプッシュすると、
        パイプラインが自動的に自分自身を更新してから
        アプリケーションスタックをデプロイする
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        employee_id    = self.node.try_get_context("employee_id")    or "my"
        github_owner   = self.node.try_get_context("github_owner")
        github_repo    = self.node.try_get_context("github_repo")
        github_branch  = self.node.try_get_context("github_branch")  or "main"
        connection_arn = self.node.try_get_context("connection_arn")
        prefix = f"n{employee_id}-cdk3"

        # ── Source: GitHub 接続 ──────────────────────────────────────
        # CodeConnections（旧 CodeStar Connections）で GitHub と接続する。
        # connection_arn は AWS コンソールで事前に作成・承認が必要。
        source = CodePipelineSource.connection(
            f"{github_owner}/{github_repo}",
            github_branch,
            connection_arn=connection_arn,
        )

        # ── Synth: CodeBuild で cdk synth を実行 ─────────────────────
        # モノレポ構成のため "cdk-pipelines/" サブディレクトリに移動してから synth する。
        # primary_output_directory で cdk.out の場所をパイプラインに伝える。
        synth_step = CodeBuildStep(
            "Synth",
            input=source,
            commands=[
                "cd cdk-pipelines",
                "pip install -r requirements.txt",
                "npx cdk synth",
            ],
            primary_output_directory="cdk-pipelines/cdk.out",
        )

        # ── Pipeline 定義 ────────────────────────────────────────────
        pipeline = CodePipeline(
            self, "Pipeline",
            pipeline_name=f"{prefix}-pipeline",
            synth=synth_step,
            cross_account_keys=False,
        )

        # ── Deploy Stage: 3層Web構成をデプロイ ──────────────────────
        pipeline.add_stage(
            ThreeTierStage(
                self, "Deploy",
                env=cdk.Environment(region="ap-northeast-1"),
            )
        )
