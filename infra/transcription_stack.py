from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct


class TranscriptionAppStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # VPC with 2 AZs, 1 NAT Gateway, public + private subnets
        self.vpc = ec2.Vpc(
            self,
            "TranscriptionVpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        # S3 Bucket for frontend static files (private, no public access)
        self.frontend_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            public_read_access=False,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Deploy static files to the bucket
        s3deploy.BucketDeployment(
            self,
            "DeployFrontend",
            sources=[s3deploy.Source.asset("../static")],
            destination_bucket=self.frontend_bucket,
        )

        # Security Group for the ALB: ingress from CloudFront managed prefix list only
        # ALB is internet-facing (required: VPC Origins don't support WebSocket)
        # but restricted to CloudFront IPs via managed prefix list — no direct public access
        self.alb_sg = ec2.SecurityGroup(
            self,
            "AlbSg",
            vpc=self.vpc,
            description="ALB security group - HTTP from CloudFront only",
            allow_all_outbound=True,
        )
        self.alb_sg.add_ingress_rule(
            ec2.Peer.prefix_list("pl-3b927c52"),
            ec2.Port.tcp(80),
            "HTTP from CloudFront managed prefix list only",
        )

        # Security Group for ECS service: ingress only from ALB SG on port 8000
        self.ecs_sg = ec2.SecurityGroup(
            self,
            "EcsSg",
            vpc=self.vpc,
            description="ECS security group - traffic from ALB only",
            allow_all_outbound=True,
        )
        self.ecs_sg.add_ingress_rule(
            self.alb_sg,
            ec2.Port.tcp(8000),
            "Traffic from ALB only",
        )

        # ECS Cluster
        self.cluster = ecs.Cluster(
            self,
            "TranscriptionCluster",
            vpc=self.vpc,
        )

        # Fargate Task Definition (256 CPU, 512 MiB memory)
        self.task_definition = ecs.FargateTaskDefinition(
            self,
            "TaskDef",
            memory_limit_mib=512,
            cpu=256,
        )

        # Grant minimal IAM permission for Transcribe streaming
        self.task_definition.add_to_task_role_policy(
            iam.PolicyStatement(
                actions=["transcribe:StartStreamTranscription"],
                resources=["*"],
            )
        )

        # ECR Repository for the Docker image (created by CDK, built via CodeBuild)
        self.ecr_repo = ecr.Repository(
            self,
            "TranscriptionRepo",
            repository_name="transcription-app",
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
        )

        # Container with Docker image from ECR
        self.task_definition.add_container(
            "TranscriptionContainer",
            image=ecs.ContainerImage.from_ecr_repository(self.ecr_repo, tag="latest"),
            logging=ecs.LogDrivers.aws_logs(stream_prefix="transcription"),
            port_mappings=[ecs.PortMapping(container_port=8000)],
        )

        # Fargate Service in private subnets with custom security group
        self.service = ecs.FargateService(
            self,
            "TranscriptionService",
            cluster=self.cluster,
            task_definition=self.task_definition,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[self.ecs_sg],
        )

        # Internet-facing ALB in public subnets (required: VPC Origins don't support WebSocket)
        # Security: restricted to CloudFront managed prefix list only — no direct public access
        self.alb = elbv2.ApplicationLoadBalancer(
            self,
            "InternalALB",
            vpc=self.vpc,
            internet_facing=True,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC
            ),
            security_group=self.alb_sg,
        )

        # HTTP listener on port 80 (open=False to prevent CDK adding 0.0.0.0/0 ingress)
        listener = self.alb.add_listener("HttpListener", port=80, open=False)

        # Target group pointing to ECS service on port 8000
        listener.add_targets(
            "EcsTarget",
            port=8000,
            targets=[self.service],
            health_check=elbv2.HealthCheck(
                path="/",
                healthy_http_codes="200",
            ),
            stickiness_cookie_duration=Duration.hours(1),
        )

        # --- CloudFront Distribution ---

        # OAC for S3 access (recommended over OAI)
        oac = cloudfront.S3OriginAccessControl(
            self,
            "OAC",
            signing=cloudfront.Signing.SIGV4_NO_OVERRIDE,
        )

        # S3 origin via OAC — bucket stays private
        s3_origin = origins.S3BucketOrigin.with_origin_access_control(
            self.frontend_bucket,
            origin_access_control=oac,
        )

        # HTTP origin for ALB (supports WebSocket, unlike VPC Origins)
        alb_origin = origins.HttpOrigin(
            self.alb.load_balancer_dns_name,
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
        )

        # Distribution: default -> S3, /ws -> ALB via HTTP origin (WebSocket)
        self.distribution = cloudfront.Distribution(
            self,
            "Distribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=s3_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            default_root_object="index.html",
            additional_behaviors={
                "/ws": cloudfront.BehaviorOptions(
                    origin=alb_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
                ),
            },
        )

        # --- Stack Outputs ---

        CfnOutput(
            self,
            "CloudFrontUrl",
            value=f"https://{self.distribution.distribution_domain_name}",
            description="URL de la distribution CloudFront",
        )

        CfnOutput(
            self,
            "BucketName",
            value=self.frontend_bucket.bucket_name,
            description="Nom du bucket S3 frontend",
        )

        CfnOutput(
            self,
            "EcrRepoUri",
            value=self.ecr_repo.repository_uri,
            description="URI du repo ECR pour l'image Docker",
        )
