# EC2 + GitHub Actions で WebアプリをCI/CDデプロイする

## 概要

alb-ec2-rds-webapp（手動デプロイ）を、**GitHub Actions + CodeDeploy** による自動デプロイに発展させるハンズオン。

コードを push するだけで自動的にビルド・デプロイが走る CI/CD パイプラインを構築する。
社内共通ライブラリ（`common-utils`）を **GitHub Packages** で管理・共有する仕組みも体験する。

## 構成

```
[GitHub リポジトリ]
  └── push
        ├── common-lib 変更 → ec2-publish-lib.yml → GitHub Packages に publish
        └── app/ 変更    → ec2-app-deploy.yml
                               ├── OIDC で AWS 認証（アクセスキー不要）
                               ├── GitHub Packages から common-utils を取得
                               ├── mvn package → webapp.war
                               ├── S3 にアップロード
                               └── CodeDeploy をトリガー
                                        ↓
                              [EC2: n123456-ec2app]
                               Tomcat 10.1 + Spring Boot WAR
                                        ↓
                          [ALB: n123456-ec2app-alb]  ← インターネット
                                        ↓
                          [RDS MySQL 8.0: n123456-ec2app-rds]
```

## 学ぶこと

| 技術・概念 | 内容 |
|-----------|------|
| **GitHub Actions** | push イベントをトリガーにビルド・デプロイを自動化するワークフロー |
| **OIDC 認証** | アクセスキー不要で GitHub Actions から AWS を操作するキーレス認証 |
| **GitHub Packages** | GitHub に組み込まれた Maven パッケージレジストリ |
| **共通ライブラリ** | 複数アプリから参照できる JAR をレジストリで管理する仕組み |
| **CodeDeploy** | EC2 への Blue/Green・ローリングデプロイを管理する AWS サービス |
| **appspec.yml** | CodeDeploy のデプロイ手順（フック・ファイル配置）を定義するファイル |
| **SSM Parameter Store** | DB パスワードなど機密設定を安全に管理する AWS サービス |
| **path filter** | 変更されたファイルパスによってワークフローの実行を制御する仕組み |

## alb-ec2-rds-webapp との比較

| 比較項目 | alb-ec2-rds-webapp | ec2-github-actions（今回） |
|---------|-------------------|--------------------------|
| デプロイ方法 | SCP / S3 手動アップロード | **GitHub Actions が自動実行** |
| 認証 | アクセスキー | **OIDC（キーレス）** |
| 共通ライブラリ | なし | **GitHub Packages で管理** |
| デプロイエージェント | なし | **CodeDeploy（appspec.yml）** |
| ビルド環境 | ローカル（mvn package） | **GitHub Actions runner** |

## ドキュメント

| ドキュメント | 内容 |
|------------|------|
| [docs/1_cloudformation.md](docs/1_cloudformation.md) | CloudFormation 構築〜CI/CD 設定〜削除まで |

## ファイル構成

```
ec2-github-actions/
├── README.md
├── architecture.drawio            # 構成図
├── common-lib/                    # 社内共通ライブラリ（GitHub Packages に publish）
│   ├── pom.xml
│   └── src/main/java/com/example/common/
│       └── ResponseWrapper.java  # API レスポンス統一クラス
├── app/                           # Spring Boot Webアプリ
│   ├── pom.xml                   # common-utils 依存・GitHub Packages 参照
│   └── src/main/
│       ├── java/com/example/webapp/
│       └── resources/
│           └── templates/index.html
├── infra/
│   └── template.yaml             # CloudFormation（VPC/EC2/ALB/RDS/CodeDeploy）
├── appspec.yml                    # CodeDeploy デプロイ定義
├── scripts/
│   ├── stop_server.sh            # BeforeInstall: Tomcat 停止
│   ├── start_server.sh           # AfterInstall: SSM から DB 設定取得 → Tomcat 起動
│   └── validate_service.sh       # ValidateService: /api/health ポーリング
└── docs/
    └── 1_cloudformation.md       # 手順書
```

> GitHub Actions ワークフローはリポジトリルートの `.github/workflows/` に配置している。
> `ec2-publish-lib.yml`（共通ライブラリ publish）と `ec2-app-deploy.yml`（アプリデプロイ）の2本。

## 前提条件

- alb-ec2-rds-webapp ハンズオン完了済み（ALB・EC2・RDS・CodeDeploy の基礎理解）
- Java 17 + Maven インストール済み
- AWS CLI v2 インストール済み
- GitHub アカウントを持ち、このリポジトリを fork / push できる状態
