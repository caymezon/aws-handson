# CDK + Auto Scaling Group で Webアプリをオートスケーリング構成にする

## 概要

cdk-webapp-pipeline（単一 EC2 構成）を、**Auto Scaling Group（ASG）** にアップグレードするハンズオン。

GitHub にコードをプッシュすると、CDK Pipelines + CodeDeploy が自動で ASG 全インスタンスへ WAR をデプロイする。
スケールアウト時は ASG のライフサイクルフックが新インスタンスへ最新 WAR を自動デプロイする。

## 構成

```
GitHub リポジトリ
  ↓ push（自動トリガー）
CodePipeline (my-cdk5-pipeline)
  ├── Source:        GitHub
  ├── Build(Synth):  CodeBuild — cdk synth
  ├── Mutate:        パイプライン自己更新
  ├── InfraDeploy:   CloudFormation — VPC / ASG / RDS / ALB
  └── AppDeploy:     ← post step
        CodeBuild: mvn package → webapp.war
        CodeDeploy: ASG の全 Tomcat に一括デプロイ
                ↓
       [ALB: my-cdk5-alb]
                ↓
       ┌─────────────────────────────┐
       │  Auto Scaling Group (ASG)   │
       │  my-cdk5-asg                │
       │  ・最小 1台 / 最大 3台      │
       │  ・CPU 60% 超でスケールアウト│
       └─────────────────────────────┘
                ↓
       [RDS: my-cdk5-rds-mysql]  ← MySQL 8.0
```

## ファイル構成

```
cdk-asg-webapp/
├── README.md
├── app.py                              # CDK アプリ エントリポイント
├── cdk.json                            # CDK 設定・Context 変数
├── requirements.txt
├── appspec.yml                         # CodeDeploy: WAR 配置手順
├── scripts/
│   ├── stop_tomcat.sh
│   ├── cleanup.sh
│   └── start_tomcat.sh
├── app/                                # Spring Boot Webアプリ（Java）
├── pipeline/
│   └── pipeline_stack.py               # CodePipeline + post step 定義
├── stages/
│   └── deploy_stage.py                 # Stage（WebappStack を内包）
├── stacks/
│   └── webapp_stack.py                 # インフラスタック（ASG + CfnOutputs）
└── components/
    └── webapp_construct.py             # ASG ベースの L3 Construct
```

## cdk-webapp-pipeline との比較

| 比較項目 | cdk-webapp-pipeline | cdk-asg-webapp |
|---------|--------------------------|----------------------|
| EC2 管理方法 | 単一 Instance リソース | Auto Scaling Group + Launch Template |
| スケーリング | なし | CPU 60% でターゲット追跡スケーリング |
| 自己回復 | なし | ALB ヘルスチェック連動で自動置換 |
| 接続方法 | SSH（キーペア必要） | SSM Session Manager（キーペア不要） |
| CodeDeploy 対象 | 名前タグで EC2 を指定 | ASG を直接指定 |
| 新インスタンスへのデプロイ | 手動 | ライフサイクルフックで自動 |

## 新しく学ぶ概念

| 概念 | 説明 |
|------|------|
| **Auto Scaling Group** | EC2 インスタンスグループを自動管理（スケールアウト/イン/自己回復） |
| **Launch Template** | ASG が新規インスタンス起動時に使う設定テンプレート |
| **ターゲット追跡ポリシー** | メトリクス目標値（CPU 60%）を維持するようにスケーリング |
| **ASG ライフサイクルフック** | スケールアウト時に CodeDeploy が自動でアプリをデプロイ |
| **SSM Session Manager** | キーペア不要でブラウザから EC2 に安全接続 |

## 前提条件

- cdk-webapp-pipeline ハンズオン完了済み
- Java 17 + Maven インストール済み
- Node.js + CDK CLI インストール済み
- CDK Bootstrap 実施済み
- GitHub アカウントを持ち、このリポジトリを push できる状態
