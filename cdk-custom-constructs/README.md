# CDK カスタム Construct で 3層構成を構築するハンズオン

## 概要

cdk-alb-ec2-rds で体験した **ALB + EC2(Tomcat) + RDS の3層構成**を、
**カスタム Construct（L3 Construct）** に切り出すハンズオン。

同じインフラを「再利用可能な部品」として定義し、CDK の本来の強みを体験する。

## 構成

```
インターネット
  ↓ HTTP(80)
[ALB: my-cdk2-alb]
  ↓ HTTP(8080)  ← SG-to-SG 制御
[EC2: my-cdk2-ap-instance]  ← Tomcat
  ↓ MySQL(3306)  ← SG-to-SG 制御
[RDS: my-cdk2-rds-mysql]  ← MySQL 8.0

┌─ ThreeTierWebConstruct ──────────────────────────────────────┐
│  VPC / SG / SSM / RDS / EC2 Role / EC2 / ALB をすべて内包  │
└──────────────────────────────────────────────────────────────┘
```

## ドキュメント

| ドキュメント | 内容 |
|------------|------|
| [docs/1_cdk.md](docs/1_cdk.md) | セットアップ〜デプロイ〜削除まで |

## ファイル構成

```
cdk-custom-constructs/
├── README.md
├── architecture.drawio               # AWS 構成図
├── app.py                            # CDK アプリ エントリポイント
├── cdk.json                          # CDK 設定・Context 変数
├── requirements.txt
├── .gitignore
├── components/
│   └── three_tier_web.py             # カスタム L3 Construct（本ハンズオンの主役）
│       ├── ThreeTierWebProps         # Construct に渡す設定値（dataclass）
│       └── ThreeTierWebConstruct    # ALB + EC2 + RDS をカプセル化
├── stacks/
│   └── three_tier_stack.py           # Props を組み立て Construct を呼ぶだけのスタック
└── docs/
    └── 1_cdk.md
```

## cdk-alb-ec2-rds との比較

| 比較項目 | cdk-alb-ec2-rds | cdk-custom-constructs |
|---------|----------------------|---------------------------|
| テーマ | CloudFormation vs CDK 比較 | Construct のカプセル化・再利用 |
| コード構成 | 全リソースを1スタックに記述 | components/ に分離 |
| スタック行数 | 約 170 行 | 約 30 行（Construct に委譲） |
| 再利用性 | なし | dev/prod で同じ Construct を使い回せる |
| 責務の分離 | なし | インフラ定義とデプロイ単位を分離 |

## 新しく学ぶ概念

| 概念 | 説明 |
|------|------|
| **カスタム Construct** | `Construct` を継承して作る独自の再利用可能コンポーネント |
| **Props パターン** | `@dataclass` で Construct の設定値をまとめる慣習 |
| **公開属性** | `self.alb` のように属性に保存してスタックから参照できるようにする |
| **Construct ID** | 同じスタック内でリソースを一意に識別するための文字列 |

## 前提条件

- cdk-alb-ec2-rds ハンズオンを完了している
- Node.js + CDK CLI インストール済み（→ [docs/setup/09_nodejs-cdk.md](../docs/setup/09_nodejs-cdk.md)）
- CDK Bootstrap 実施済み（初回のみ必要）
