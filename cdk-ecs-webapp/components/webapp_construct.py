from dataclasses import dataclass, field
from aws_cdk import (
    Duration,
    RemovalPolicy,
    SecretValue,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
    aws_ssm as ssm,
    aws_ecr as ecr,
    aws_ecs as ecs,
    aws_logs as logs,
)
from constructs import Construct


@dataclass
class WebappProps:
    """
    WebappConstruct に渡す設定値をまとめた Props クラス。
    cdk-asg-webapp との主な違い:
      - asg_min / asg_max / asg_desired → task_cpu / task_memory / desired_count
      - tomcat_version を削除（Dockerfile で管理）
    """
    employee_id: str
    db_password: str
    task_cpu: int = field(default=256)
    task_memory: int = field(default=512)
    desired_count: int = field(default=1)


class WebappConstruct(Construct):
    """
    ALB + ECS Fargate(Tomcat コンテナ) + RDS の3層Webアーキテクチャ。

    cdk-asg-webapp との主な違い:
      - EC2(Launch Template + ASG) → ECS Fargate（サーバーレスコンテナ）
      - CodeDeploy + appspec.yml → Docker イメージ + ECR + タスク定義更新
      - SSM Session Manager → ECS Exec（コンテナへのデバッグ接続）
      - スケーリング: CPU 自動スケール → desired_count を直接変更
      - 初回デプロイ: ECR が空のため public Tomcat をプレースホルダーとして使用

    --- 公開属性 ---
      self.alb              : ApplicationLoadBalancer
      self.ecs_service      : FargateService
      self.db_instance      : DatabaseInstance (RDS)
      self.vpc              : Vpc
      self.ecr_repository   : Repository (ECR)
      self.cluster          : Cluster (ECS)
      self.task_def_family  : str  (タスク定義ファミリー名)
      self.container_name   : str  (コンテナ名)
    """

    def __init__(self, scope: Construct, id: str, *, props: WebappProps) -> None:
        super().__init__(scope, id)

        prefix = f"{props.employee_id}-cdk6"

        # ============================================================
        # VPC
        # ============================================================
        self.vpc = ec2.Vpc(
            self, "VPC",
            vpc_name=f"{prefix}-vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # S3 VPC ゲートウェイエンドポイント
        # ECS Fargate が ECR からイメージを pull する際、レイヤーデータは S3 経由でダウンロードされる。
        # ゲートウェイエンドポイント経由にすることで通信を VPC 内に閉じる（無料）。
        self.vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )

        # ============================================================
        # Security Groups
        # ============================================================
        alb_sg = ec2.SecurityGroup(
            self, "ALBSecurityGroup",
            vpc=self.vpc,
            security_group_name=f"{prefix}-alb-sg",
            description=f"{prefix} ALB SG",
        )
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "HTTP from internet")

        ecs_sg = ec2.SecurityGroup(
            self, "ECSSecurityGroup",
            vpc=self.vpc,
            security_group_name=f"{prefix}-ecs-sg",
            description=f"{prefix} ECS Fargate Task SG",
        )
        # ALB からのみ 8080 を許可（SG 間参照で IP 管理不要）
        ecs_sg.add_ingress_rule(alb_sg, ec2.Port.tcp(8080), "Tomcat from ALB SG only (SG-to-SG)")

        rds_sg = ec2.SecurityGroup(
            self, "RDSSecurityGroup",
            vpc=self.vpc,
            security_group_name=f"{prefix}-rds-sg",
            description=f"{prefix} RDS MySQL SG",
        )
        rds_sg.add_ingress_rule(ecs_sg, ec2.Port.tcp(3306), "MySQL from ECS SG only (SG-to-SG)")

        # ============================================================
        # SSM Parameter Store（DBパスワードを安全に管理）
        # ECS タスク定義の secrets フィールドで参照し、起動時にコンテナへ環境変数として注入する
        # ============================================================
        db_password_param = ssm.StringParameter(
            self, "DBPasswordParam",
            parameter_name=f"/{props.employee_id}/cdk6/db-password",
            string_value=props.db_password,
            description=f"RDS MySQL master password for {prefix}",
        )

        # ============================================================
        # RDS MySQL
        # ============================================================
        self.db_instance = rds.DatabaseInstance(
            self, "RDSInstance",
            database_name="sampledb",
            engine=rds.DatabaseInstanceEngine.mysql(
                version=rds.MysqlEngineVersion.VER_8_0,
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.MICRO,
            ),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
            ),
            security_groups=[rds_sg],
            credentials=rds.Credentials.from_username(
                "admin",
                password=SecretValue.unsafe_plain_text(props.db_password),
            ),
            instance_identifier=f"{prefix}-rds-mysql",
            multi_az=False,
            publicly_accessible=False,
            allocated_storage=20,
            backup_retention=Duration.days(0),
            delete_automated_backups=True,
            deletion_protection=False,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ============================================================
        # ECR Repository（Docker イメージの保管場所）
        # cdk-asg-webapp の S3 Artifact Bucket に相当するが、コンテナイメージを格納する
        # ============================================================
        self.ecr_repository = ecr.Repository(
            self, "ECRRepository",
            repository_name=f"{prefix}-app",
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
        )

        # ============================================================
        # ECS Cluster（Fargate タスクの実行環境）
        # ============================================================
        self.cluster = ecs.Cluster(
            self, "ECSCluster",
            cluster_name=f"{prefix}-cluster",
            vpc=self.vpc,
        )

        # CloudWatch Logs グループ（コンテナログの出力先）
        log_group = logs.LogGroup(
            self, "LogGroup",
            log_group_name=f"/ecs/{prefix}-app",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_WEEK,
        )

        # ============================================================
        # IAM Roles for ECS
        # cdk-asg-webapp の EC2 Role に相当するが、ECS 用に分割される:
        #   - 実行ロール: ECR pull / CloudWatch Logs / SSM secrets 取得
        #   - タスクロール: アプリが使う権限 + ECS Exec（デバッグ接続）
        # ============================================================
        task_execution_role = iam.Role(
            self, "TaskExecutionRole",
            role_name=f"{prefix}-ecs-exec-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                # ECR pull / CloudWatch Logs 書き込みに必要
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                ),
            ],
        )
        # SSM Parameter Store から DB パスワードを取得する権限（secrets フィールド用）
        db_password_param.grant_read(task_execution_role)

        task_role = iam.Role(
            self, "TaskRole",
            role_name=f"{prefix}-ecs-task-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        # ECS Exec（コンテナへのデバッグ接続）に必要な SSM メッセージ権限
        task_role.add_to_principal_policy(iam.PolicyStatement(
            actions=[
                "ssmmessages:CreateControlChannel",
                "ssmmessages:CreateDataChannel",
                "ssmmessages:OpenControlChannel",
                "ssmmessages:OpenDataChannel",
            ],
            resources=["*"],
        ))

        # ============================================================
        # ECS Fargate Task Definition（コンテナの実行設定）
        # cdk-asg-webapp の Launch Template に相当する
        # ============================================================
        self.task_def_family = f"{prefix}-task"
        self.container_name  = f"{prefix}-app"

        task_definition = ecs.FargateTaskDefinition(
            self, "TaskDefinition",
            family=self.task_def_family,
            cpu=props.task_cpu,
            memory_limit_mib=props.task_memory,
            execution_role=task_execution_role,
            task_role=task_role,
        )

        rds_endpoint = self.db_instance.db_instance_endpoint_address

        # コンテナ定義
        # 初回デプロイ時は ECR が空のため public の Tomcat をプレースホルダーとして使用する。
        # GitHub Actions が ECR にイメージをプッシュした後、
        # タスク定義を更新して実際の Spring Boot アプリに切り替える。
        task_definition.add_container(
            "AppContainer",
            container_name=self.container_name,
            image=ecs.ContainerImage.from_registry(
                "public.ecr.aws/docker/library/tomcat:10.1-jdk17-corretto"
            ),
            environment={
                # DB_HOST は CloudFormation デプロイ時に RDS エンドポイントが解決される
                "DB_HOST": rds_endpoint,
            },
            secrets={
                # DB_PASSWORD は ECS 起動時に SSM Parameter Store から取得して環境変数として注入される
                # cdk-asg-webapp では UserData でシェルスクリプトから取得していた処理と同等
                "DB_PASSWORD": ecs.Secret.from_ssm_parameter(db_password_param),
            },
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="app",
                log_group=log_group,
            ),
            port_mappings=[
                ecs.PortMapping(container_port=8080, protocol=ecs.Protocol.TCP)
            ],
        )

        # ============================================================
        # ALB
        # ============================================================
        self.alb = elbv2.ApplicationLoadBalancer(
            self, "ALB",
            load_balancer_name=f"{prefix}-alb",
            vpc=self.vpc,
            internet_facing=True,
            security_group=alb_sg,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        http_listener = self.alb.add_listener("HTTPListener", port=80, open=False)

        # Fargate はインスタンス IP ではなく タスク IP で ALB に登録されるため
        # TargetType.IP を指定する（cdk-asg-webapp の INSTANCE と異なる点）
        target_group = elbv2.ApplicationTargetGroup(
            self, "TargetGroup",
            target_group_name=f"{prefix}-tg",
            vpc=self.vpc,
            port=8080,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            # 旧タスクの接続ドレイン待機時間: デフォルト 300s → 30s に短縮してデプロイを高速化
            deregistration_delay=Duration.seconds(30),
            health_check=elbv2.HealthCheck(
                path="/",
                port="8080",
                protocol=elbv2.Protocol.HTTP,
                # WAR デプロイ前 or プレースホルダー Tomcat は "/" に 404 を返すため含める
                healthy_http_codes="200-404",
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
                interval=Duration.seconds(15),
                timeout=Duration.seconds(5),
            ),
        )

        http_listener.add_target_groups("DefaultTargets", target_groups=[target_group])

        # ============================================================
        # ECS Fargate Service（cdk-asg-webapp の AutoScalingGroup に相当）
        # ============================================================
        self.ecs_service = ecs.FargateService(
            self, "ECSService",
            service_name=f"{prefix}-service",
            cluster=self.cluster,
            task_definition=task_definition,
            desired_count=props.desired_count,
            # パブリックサブネット + パブリック IP 割り当てで NAT ゲートウェイなしに ECR から pull する
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            assign_public_ip=True,
            security_groups=[ecs_sg],
            # ヘルスチェックグレースピリオド: Tomcat + Spring Boot WAR の初期化 + RDS 接続を含めて 120s
            health_check_grace_period=Duration.seconds(120),
            # ローリングデプロイ設定
            # 最小 50%: 旧タスクを停止する前に新タスクが起動済みであること
            # 最大 200%: 新旧タスクを同時に起動できる（デプロイ中は一時的に倍のタスクが動く）
            min_healthy_percent=50,
            max_healthy_percent=200,
            # ECS Exec を有効化（ecs execute-command でコンテナ内のシェルに接続できる）
            enable_execute_command=True,
        )

        # ECS サービスを ALB ターゲットグループに登録
        self.ecs_service.attach_to_application_target_group(target_group)
