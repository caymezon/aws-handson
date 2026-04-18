# ALB + EC2(Tomcat) + RDS Webアプリハンズオン

## 概要

ALB + EC2 + RDS では Tomcat に静的HTMLを配置して3層構成を確認した。
このハンズオンでは、**Spring Boot + Maven** で作成した WebアプリケーションをWARファイルとしてビルドし、
Tomcat にデプロイして RDS MySQL に JDBC で接続する **本格的なWebアプリ**を体験する。

## 構成

```
インターネット
  ↓ HTTP(80)
[ALB: my-webapp-alb]
  ↓ HTTP(8080)
[EC2: my-webapp-ap-instance]
  Tomcat + Spring Boot WAR（webapp.war）
  ↓ JDBC(3306)
[RDS: my-webapp-rds-mysql]  ← MySQL 8.0 / sampledb
```

## 学ぶこと

| 技術 | 内容 |
|------|------|
| **Spring Boot** | Java Webアプリの標準フレームワーク |
| **Maven** | Javaのビルドツール（`mvn package` でWARを生成） |
| **JDBC（JdbcTemplate）** | JavaからDBに接続する標準API |
| **WAR デプロイ** | ビルドしたアプリをTomcatに配置する手順 |
| **環境変数でDB接続** | DBホスト・パスワードをSSMから安全に注入 |

## ALB + EC2 + RDS との比較

| 比較項目 | ALB + EC2 + RDS | ALB + EC2 + RDS（Webアプリ）今回 |
|---------|-----------|-----------------|
| EC2のコンテンツ | 静的HTML（手書き） | **Spring Boot WAR（Mavenビルド）** |
| DB接続 | なし | **JdbcTemplateでRDS接続** |
| 画面 | テキストのみ | **アイテム一覧・追加・削除のCRUD画面** |
| デプロイ方法 | UserDataに直接記述 | **WARファイルをSCP/S3経由で配布** |
| DB設定の渡し方 | なし | **環境変数（SSMから取得）** |

## ドキュメント

| ドキュメント | 内容 |
|------------|------|
| [docs/0_app.md](docs/0_app.md) | Webアプリのビルド手順（mvn package） |
| [docs/1_console.md](docs/1_console.md) | コンソールで手動構築 + アプリデプロイ（⓪〜⑯） |
| [docs/2_cloudformation.md](docs/2_cloudformation.md) | CloudFormationで一括構築 |

## ファイル構成

```
alb-ec2-rds-webapp/
├── README.md
├── template.yaml              # CloudFormationテンプレート
├── app/                       # Spring Boot Mavenプロジェクト
│   ├── pom.xml
│   └── src/main/
│       ├── java/com/example/webapp/
│       │   ├── WebAppApplication.java
│       │   ├── controller/ItemController.java
│       │   ├── model/Item.java
│       │   └── repository/ItemRepository.java
│       └── resources/
│           ├── application.properties
│           ├── schema.sql
│           └── templates/index.html
└── docs/
    ├── 0_app.md               # アプリビルド手順書
    ├── 1_console.md           # コンソール版手順書
    └── 2_cloudformation.md   # CloudFormation版手順書
```

## 前提条件

- Java 17 以上インストール済み
- Maven 3.9 以上インストール済み
- AWS CLI v2 インストール済み
- ALB + EC2 + RDS を完了している（ALB・TG・ヘルスチェックの理解）
