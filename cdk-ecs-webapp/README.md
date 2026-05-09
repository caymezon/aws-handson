# CDK + ECS Fargate で Webアプリをコンテナ化する

## 概要

cdk-asg-webapp（EC2 + Auto Scaling Group 構成）を、**ECS Fargate（サーバーレスコンテナ）** にアップグレードするハンズオン。

EC2 インスタンス管理から解放され、Docker コンテナとして Spring Boot アプリを動かす体験をする。

## 構成

```
【インフラ担当】
GitHub リポジトリ
  ↓ push（自動トリガー・常に起動）
CodePipeline (my-cdk6-pipeline)
  ├── Source:      GitHub
  ├── Build(Synth): CodeBuild — cdk synth
  ├── Mutate:      パイプライン自己更新
  └── InfraDeploy: CloudFormation — VPC / ECR / ECS / RDS / ALB

【アプリ担当】
GitHub リポジトリ
  ↓ push（app/ または Dockerfile 変更時のみ）
GitHub Actions (Deploy App to ECS)
  1. Docker ビルド（Maven → WAR → Tomcat コンテナ）
  2. ECR にプッシュ
  3. タスク定義を更新（プレースホルダー → 実イメージ）
  4. ECS サービスをローリングデプロイ（〜2〜3 分）

                ↓
       [ALB: my-cdk6-alb]
                ↓
       ECS Fargate Service (my-cdk6-service)
       ・コンテナ: Tomcat 10.1 + Spring Boot WAR
       ・CPU: 256 units / Memory: 512 MiB
       ・タスク数: 1（desired_count で変更可）
                ↓
       [RDS: my-cdk6-rds-mysql]  ← MySQL 8.0
```

## ファイル構成

```
cdk-ecs-webapp/
├── README.md
├── app.py                              # CDK アプリ エントリポイント
├── cdk.json                            # CDK 設定・Context 変数
├── requirements.txt
├── Dockerfile                          # ← cdk-asg-webapp にはない（コンテナ化の核心）
├── app/                                # Spring Boot アプリ（Java）
│   └── src/...
├── pipeline/
│   └── pipeline_stack.py               # CodePipeline 定義（インフラのみ）
├── stages/
│   └── deploy_stage.py                 # Stage（WebappStack を内包）
├── stacks/
│   └── webapp_stack.py                 # インフラスタック（ECS + CfnOutputs）
└── components/
    └── webapp_construct.py             # ECS ベースの L3 Construct
```

GitHub Actions ワークフロー（リポジトリルート）:
```
.github/workflows/
└── ecs-app-deploy.yml                  # app/ または Dockerfile 変更時に ECS デプロイ
```

## cdk-asg-webapp との比較

| 比較項目 | cdk-asg-webapp | cdk-ecs-webapp |
|---------|----------------|----------------|
| 実行環境 | EC2（Launch Template + ASG） | ECS Fargate（サーバーレスコンテナ） |
| デプロイ形式 | WAR → S3 → CodeDeploy | Docker Image → ECR → ECS タスク更新 |
| インフラ管理 | EC2 OS・エージェント管理が必要 | サーバーレス（EC2 管理不要） |
| スケーリング | CPU 自動スケール（ASG ポリシー） | desired_count を直接変更（シンプル） |
| デバッグ接続 | SSM Session Manager（EC2 に接続） | ECS Exec（コンテナに直接接続） |
| 設定ファイル | appspec.yml + scripts/ | Dockerfile のみ |

## 新しく学ぶ概念

| 概念 | 説明 |
|------|------|
| **Dockerfile** | コンテナイメージのビルド手順を記述するファイル |
| **マルチステージビルド** | ビルド環境（Maven）と実行環境（Tomcat）を分離してイメージを軽量化 |
| **ECR（Elastic Container Registry）** | Docker イメージを保管する AWS マネージドレジストリ |
| **ECS Fargate** | EC2 なしでコンテナを実行できるサーバーレス実行環境 |
| **タスク定義** | コンテナの CPU/メモリ・環境変数・IAM ロールなどを定義する設定 |
| **ECS Service** | タスクのスケーリング・ヘルスチェック・ALB 連携を管理する |
| **ローリングデプロイ** | 旧コンテナを停止しながら新コンテナを順次起動する無停止デプロイ |
| **ECS Exec** | コンテナ内のシェルに AWS CLI から直接アクセスするデバッグ機能 |
| **OIDC 認証** | アクセスキー不要で GitHub Actions から AWS を操作するキーレス認証 |
| **インフラ/アプリ分離デプロイ** | CDK Pipelines（インフラ）と GitHub Actions（アプリ）で役割を分担 |

## 前提条件

- cdk-asg-webapp ハンズオン完了済み（または cdk-webapp-pipeline 完了済み）
- Java 17 + Maven インストール済み
- Node.js + CDK CLI インストール済み
- CDK Bootstrap 実施済み
- GitHub アカウントを持ち、このリポジトリを push できる状態
- Docker Desktop インストール不要（ビルドは GitHub Actions runner で実行される）
