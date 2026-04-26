# CDK Pipelines で CI/CD パイプラインを構築するハンズオン

## 概要

cdk-custom-constructs で体験した **ALB + EC2(Tomcat) + RDS の3層構成**を、
**CDK Pipelines** を使って CI/CD パイプライン化するハンズオン。

GitHub にコードをプッシュするだけで AWS CodePipeline が起動し、
自動的に 3層Webインフラをデプロイ・更新する仕組みを体験する。

## 構成

```
GitHub リポジトリ
  ↓ push（自動トリガー）
CodePipeline (my-cdk3-pipeline)
  ├── Source:  GitHub (CodeConnections 経由)
  ├── Build:   CodeBuild — cdk synth
  ├── Mutate:  パイプライン自身を自動更新（セルフミューテーション）
  └── Deploy:  CloudFormation — ThreeTierStack
                  ↓
         [ALB: my-cdk3-alb]
                  ↓
         [EC2: my-cdk3-ap-instance]  ← Tomcat
                  ↓
         [RDS: my-cdk3-rds-mysql]    ← MySQL 8.0
```

## ドキュメント

| ドキュメント | 内容 |
|------------|------|
| [docs/1_cdk.md](docs/1_cdk.md) | セットアップ〜デプロイ〜削除まで |

## ファイル構成

```
cdk-pipelines/
├── README.md
├── app.py                            # CDK アプリ エントリポイント
├── cdk.json                          # CDK 設定・Context 変数
├── requirements.txt
├── .gitignore
├── pipeline/
│   └── pipeline_stack.py             # CodePipeline 定義スタック
├── stages/
│   └── three_tier_stage.py           # Stage（デプロイ対象をまとめる単位）
├── stacks/
│   └── three_tier_stack.py           # 3層Web構成スタック（Props + Outputs）
├── components/
│   └── three_tier_web.py             # カスタム L3 Construct（再利用）
└── docs/
    └── 1_cdk.md
```

## このハンズオンで体験できること・できないこと

### 体験できること（インフラの CI/CD）

git push するだけで以下が自動実行される:

| 自動化される内容 | 仕組み |
|---------------|------|
| VPC / EC2 / RDS / ALB などのインフラ構築・更新 | CloudFormation による自動デプロイ |
| インフラ変更の自動反映（SG ルール追加・インスタンスタイプ変更など） | push → CodePipeline → cdk synth → CloudFormation |
| パイプライン自体の定義変更も自動反映 | セルフミューテーション |

### 体験できないこと（アプリの CI/CD）

**HTML や WAR などのアプリファイルを push で自動反映することはできない。**

理由: このハンズオンではアプリの内容（HTML）を EC2 の **UserData** に埋め込んでいる。  
UserData は EC2 の**初回起動時にのみ実行**される仕組みであるため、  
push しても既存 EC2 上の HTML ファイルは書き換えられない。

```
push → CloudFormation が UserData のメタデータを更新
     → 既存 EC2 はそのまま稼働し続ける（UserData は再実行されない）
     → /opt/tomcat/webapps/ROOT/index.html は変わらない ← ここが限界
```

HTML を更新したい場合は、EC2 に SSH して手動で書き換えるしかない。

### `cdk-webapp-pipeline` を学ぶ動機

アプリも含めて push で自動デプロイするには **CodeDeploy** が必要。  
次のハンズオン `cdk-webapp-pipeline` では以下を追加で学ぶ:

| 追加する仕組み | 効果 |
|-------------|------|
| CodeDeploy | EC2 上の Tomcat に WAR をホットデプロイ |
| appspec.yml | デプロイ手順（停止→配置→起動）をコードで定義 |
| mvn package | Maven で WAR をビルドしてから CodeDeploy に渡す |

これにより「push → インフラ更新 ＋ アプリ更新」が完全に自動化される。

---

## cdk-custom-constructs との比較

| 比較項目 | cdk-custom-constructs | cdk-pipelines |
|---------|----------------------|---------------|
| テーマ | Construct のカプセル化・再利用 | CI/CD パイプラインによる自動デプロイ |
| デプロイ方法 | `cdk deploy`（手動） | GitHub push → 自動 |
| インフラ変更の反映 | 毎回 `cdk deploy` を手動実行 | push するだけで自動反映 |
| パイプライン管理 | なし | CodePipeline がデプロイを管理 |
| セルフミューテーション | なし | パイプライン自体もコードで管理・自動更新 |

## 新しく学ぶ概念

| 概念 | 説明 |
|------|------|
| **CDK Pipelines** | CDK アプリの CI/CD を定義する高レベル Construct ライブラリ |
| **Stage** | パイプラインのデプロイ単位。複数スタックをひとまとめにできる |
| **セルフミューテーション** | パイプライン自身のコードを変更すると自動的に更新される仕組み |
| **CodeConnections** | GitHub など外部 SCM と AWS を接続するサービス（旧 CodeStar Connections） |
| **Synth Step** | CodeBuild で `cdk synth` を実行し Cloud Assembly を生成するステップ |

## 前提条件

- cdk-custom-constructs ハンズオンを完了している
- Node.js + CDK CLI インストール済み（→ [docs/setup/09_nodejs-cdk.md](../docs/setup/09_nodejs-cdk.md)）
- CDK Bootstrap 実施済み（初回のみ必要）
- GitHub アカウントを持ち、このリポジトリを push できる状態
