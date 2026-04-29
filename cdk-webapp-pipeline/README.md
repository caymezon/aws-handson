# CDK Pipelines で Spring Boot Webアプリを CI/CD デプロイするハンズオン

## 概要

alb-ec2-rds-webapp（CloudFormation 版）で構築した **Spring Boot + RDS の3層Webアプリ**を、
**CDK Pipelines + CodeDeploy** で CI/CD パイプライン化するハンズオン。

GitHub にコードをプッシュするだけで、Maven ビルド（WAR 生成）から
EC2/Tomcat への自動デプロイまでが走る仕組みを体験する。

## 構成

```
GitHub リポジトリ（app/ に Java ソース、cdk-webapp-pipeline/ に CDK コード）
  ↓ push（自動トリガー）
CodePipeline (my-cdk4-pipeline)
  ├── Source:        GitHub (CodeConnections 経由)
  ├── Build(Synth):  CodeBuild — cdk synth
  ├── Mutate:        パイプライン自己更新
  ├── InfraDeploy:   CloudFormation — VPC / EC2 / RDS / ALB / CodeDeploy 設定
  └── AppDeploy:     ← post step
        CodeBuild: mvn package → webapp.war
        CodeDeploy: EC2/Tomcat にホットデプロイ
                ↓
       [ALB: my-cdk4-alb]
                ↓
       [EC2: my-cdk4-ap-instance]  ← Tomcat + Spring Boot WAR
                ↓
       [RDS: my-cdk4-rds-mysql]    ← MySQL 8.0
```

## ファイル構成

```
cdk-webapp-pipeline/
├── README.md
├── app.py                              # CDK アプリ エントリポイント
├── cdk.json                            # CDK 設定・Context 変数
├── requirements.txt
├── .gitignore
├── appspec.yml                         # CodeDeploy: WAR 配置手順
├── scripts/
│   ├── stop_tomcat.sh                  # CodeDeploy ライフサイクルフック
│   ├── cleanup.sh
│   └── start_tomcat.sh
├── app/                                # Spring Boot Webアプリ（Java）
│   ├── pom.xml
│   └── src/main/java/com/example/webapp/
│       ├── WebAppApplication.java
│       ├── controller/ItemController.java
│       ├── model/Item.java
│       └── repository/ItemRepository.java
├── pipeline/
│   └── pipeline_stack.py               # CodePipeline + post step 定義
├── stages/
│   └── webapp_stage.py                 # Stage（WebappStack を内包）
├── stacks/
│   └── webapp_stack.py                 # インフラスタック（Props + CfnOutputs）
└── components/
    └── webapp_construct.py             # カスタム L3 Construct
```

## cdk-pipelines との比較

| 比較項目 | cdk-pipelines | cdk-webapp-pipeline |
|---------|--------------|---------------------|
| 何を自動デプロイするか | インフラのみ（Tomcat は空で起動） | インフラ ＋ Spring Boot WAR |
| アプリコード | なし | `app/` 配下に Java/Spring Boot |
| ビルドステップ | `cdk synth` のみ | `cdk synth` ＋ `mvn package` |
| デプロイ手段 | CloudFormation のみ | CloudFormation ＋ CodeDeploy |
| 主な学習テーマ | CDK Pipelines の基本・セルフミューテーション | CodeDeploy / WAR デプロイ / env_from_cfn_outputs |

## 新しく学ぶ概念

| 概念 | 説明 |
|------|------|
| **CodeDeploy** | EC2 への Webアプリのホットデプロイを管理するサービス |
| **appspec.yml** | CodeDeploy のデプロイ手順（ファイル配置・フック）を定義するファイル |
| **デプロイバンドル** | appspec.yml + WAR + scripts を ZIP にまとめたもの |
| **ライフサイクルフック** | デプロイの各フェーズ（停止・クリーンアップ・起動）で実行するスクリプト |
| **env_from_cfn_outputs** | CDK Pipelines でスタックの CfnOutput を後続ステップへ渡す仕組み |

## 前提条件

- Java 17 + Maven インストール済み
- Node.js + CDK CLI インストール済み
- CDK Bootstrap 実施済み
- GitHub アカウントを持ち、このリポジトリを push できる状態
