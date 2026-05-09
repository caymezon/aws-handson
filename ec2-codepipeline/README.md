# EC2 + CodePipeline（Code 3兄弟）で WebアプリをCI/CDデプロイする

## 概要

ec2-github-actions（GitHub Actions + CodeDeploy）を、**AWS Code 3兄弟（CodeCommit・CodeBuild・CodeDeploy）+ CodePipeline** による完全 AWS CI/CD に移行するハンズオン。

GitHub を一切使わず、コードを CodeCommit に push するだけで自動的にビルド・デプロイが走るパイプラインを構築する。
社内共通ライブラリ（`common-utils`）を **AWS CodeArtifact** で管理・共有する仕組みも体験する。

## 構成

```
[CodeCommit リポジトリ: n123456-cpapp]
  └── git push (自動トリガー)
        ↓
[CodePipeline: n123456-cp-pipeline]
  ├── Stage 1: Source  — CodeCommit からソース取得
  ├── Stage 2: Build   — CodeBuild (buildspec.yml)
  │     ├── CodeArtifact 認証トークン取得
  │     ├── common-lib を CodeArtifact に publish
  │     ├── CodeArtifact から common-utils を取得
  │     └── mvn package → webapp.war
  └── Stage 3: Deploy  — CodeDeploy → EC2
              ↓
  [EC2: n123456-cpapp]
   Tomcat 10.1 + Spring Boot WAR
              ↓
  [ALB: n123456-cp-alb]  ← インターネット
              ↓
  [RDS MySQL 8.0: n123456-cpapp-rds]
```

## 学ぶこと

| 技術・概念 | 内容 |
|-----------|------|
| **CodeCommit** | AWS マネージド Git リポジトリ（IAM 認証） |
| **CodeBuild** | ビルド処理を実行するマネージドサービス（`buildspec.yml` で定義） |
| **buildspec.yml** | CodeBuild のビルド手順（install / pre_build / build / artifacts）を定義するファイル |
| **CodeDeploy** | EC2 へのデプロイを管理する AWS サービス |
| **CodePipeline** | Source → Build → Deploy のステージを自動実行するオーケストレーター |
| **CodeArtifact** | AWS マネージドな Maven/npm/PyPI パッケージレジストリ |
| **Maven Central プロキシ** | CodeArtifact が外部リポジトリのキャッシュとして機能する仕組み |
| **一時認証トークン** | `codeartifact get-authorization-token` で取得する短期有効な認証情報 |

## ec2-github-actions との比較

| 比較項目 | ec2-github-actions | ec2-codepipeline（今回） |
|---------|-------------------|------------------------|
| ソース管理 | GitHub | **AWS CodeCommit** |
| ビルド実行 | GitHub Actions runner | **AWS CodeBuild** |
| ビルド定義ファイル | `.github/workflows/*.yml` | **`buildspec.yml`** |
| 共通ライブラリ | GitHub Packages | **AWS CodeArtifact** |
| 認証 | OIDC（GitHub ↔ AWS） | **IAM ロール（CodeBuild が直接使用）** |
| パイプライン定義 | GitHub Actions ワークフロー | **CodePipeline（AWS コンソール管理）** |
| 全サービス | GitHub + AWS 混在 | **完全 AWS** |

## ドキュメント

| ドキュメント | 内容 |
|------------|------|
| [docs/1_cloudformation.md](docs/1_cloudformation.md) | CloudFormation 構築〜CodeCommit push〜パイプライン確認〜削除まで |

## ファイル構成

```
ec2-codepipeline/
├── README.md
├── architecture.drawio            # 構成図
├── common-lib/                    # 社内共通ライブラリ（CodeArtifact に publish）
│   ├── pom.xml
│   └── src/main/java/com/example/common/
│       └── ResponseWrapper.java  # API レスポンス統一クラス
├── app/                           # Spring Boot Webアプリ
│   ├── pom.xml                   # common-utils 依存・CodeArtifact 参照
│   └── src/main/
│       ├── java/com/example/webapp/
│       └── resources/
│           └── templates/index.html
├── infra/
│   └── template.yaml             # CloudFormation（VPC/EC2/ALB/RDS/CodeCommit/
│                                 #   CodeBuild/CodeDeploy/CodeArtifact/CodePipeline）
├── buildspec.yml                  # CodeBuild ビルド定義
├── appspec.yml                    # CodeDeploy デプロイ定義
├── scripts/
│   ├── stop_server.sh            # BeforeInstall: Tomcat 停止
│   ├── start_server.sh           # AfterInstall: SSM から DB 設定取得 → Tomcat 起動
│   └── validate_service.sh       # ValidateService: /api/health ポーリング
└── docs/
    └── 1_cloudformation.md       # 手順書
```

## 前提条件

- ec2-github-actions ハンズオン完了済み（CodeDeploy・appspec.yml・SSM Parameter Store の理解）
- Java 17 + Maven インストール済み
- AWS CLI v2 インストール済み
- Git インストール済み（CodeCommit への HTTPS push）
