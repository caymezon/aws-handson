# CDK で ALB + EC2(Tomcat) + RDS 3層構成ハンズオン

## 概要

CloudFormation で構築した **ALB + EC2(Tomcat) + RDS の3層構成**（alb-ec2-rds）を、
**AWS CDK（Python）** で再現するハンズオン。

CloudFormation では 460 行必要だった YAML を、Python コード約 200 行で記述できることを体験する。

## 構成

```
インターネット
  ↓ HTTP(80)
[ALB: my-cdk-alb-alb]  ← インターネット向け / パブリックサブネット 2AZ
  ↓ HTTP(8080)  ← ALB SG → EC2 SG（SG-to-SG 制御）
[EC2: my-cdk-alb-ap-instance]  ← Tomcat / パブリックサブネット AZ-a
  ↓ MySQL(3306)  ← EC2 SG → RDS SG（SG-to-SG 制御）
[RDS: my-cdk-alb-rds-mysql]  ← MySQL 8.0 / プライベートサブネット AZ-a

[VPC: my-cdk-alb-vpc (10.0.0.0/16)]
  ├── パブリックサブネット [AZ-a]  ← ALB + EC2
  ├── パブリックサブネット [AZ-b]  ← ALB（2AZ 必須）
  ├── プライベートサブネット [AZ-a]  ← RDS 配置
  └── プライベートサブネット [AZ-b]  ← DBサブネットグループ用
```

## ドキュメント

| ドキュメント | 内容 |
|------------|------|
| [docs/1_cdk.md](docs/1_cdk.md) | CDK でのセットアップ〜デプロイ〜削除まで |

## ファイル構成

```
cdk-alb-ec2-rds/
├── README.md
├── architecture.drawio      # AWS 構成図
├── app.py                   # CDK アプリ エントリポイント
├── cdk.json                 # CDK 設定・Context 変数
├── requirements.txt         # Python 依存パッケージ
├── .gitignore
├── stacks/
│   ├── __init__.py
│   └── alb_ec2_rds_stack.py  # CDK スタック本体
└── docs/
    └── 1_cdk.md             # CDK 版手順書
```

## CloudFormation 版との比較

| 比較項目 | CloudFormation (alb-ec2-rds) | CDK（このハンズオン） |
|---------|------------------------------|-------------------|
| 記述言語 | YAML | Python |
| コード量 | 約 460 行 | 約 200 行 |
| VPC 定義 | 15+ リソースを手動記述 | `ec2.Vpc` 1つで自動生成 |
| デプロイ | `aws cloudformation deploy` | `cdk deploy` |
| 削除 | `aws cloudformation delete-stack` | `cdk destroy` |
| 差分確認 | 変更セット（手動作成） | `cdk diff`（自動） |

## 新しく学ぶ概念

| 概念 | 説明 |
|------|------|
| **CDK App** | `app.py` がエントリポイント。`cdk synth` でここから CloudFormation テンプレートを生成 |
| **CDK Stack** | 1つの CloudFormation スタックに対応する単位 |
| **L2 Construct** | AWS がベストプラクティスを組み込んだ高レベルな抽象クラス（`ec2.Vpc` 等） |
| **CDK Context** | `cdk.json` に書くデプロイ設定。`-c key=value` で上書き可能 |
| **CDK Bootstrap** | CDK が AWS にデプロイするために必要な事前準備（初回のみ） |
| **cdk synth** | Python コードから CloudFormation テンプレートを生成（デプロイなし） |
| **cdk diff** | 現在のデプロイ状態と新しいコードの差分を表示 |

## 前提条件

- alb-ec2-rds ハンズオンを完了している
- Node.js 18 以上（CDK CLI に必要）
- Python 3.9 以上
- AWS CLI v2、認証情報設定済み
