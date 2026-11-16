import * as cdk from 'aws-cdk-lib'
import { Construct } from 'constructs'
import * as ec2 from 'aws-cdk-lib/aws-ec2'
import * as ecs from 'aws-cdk-lib/aws-ecs'
import * as iam from 'aws-cdk-lib/aws-iam'
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2'
import * as cognito from 'aws-cdk-lib/aws-cognito'
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager'
import * as logs from 'aws-cdk-lib/aws-logs'
import * as s3 from 'aws-cdk-lib/aws-s3'
import * as ecrAssets from 'aws-cdk-lib/aws-ecr-assets'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../..')

// Cross-region inference profile the server invokes. The IAM policy below is
// scoped to this profile and its underlying model, so changing the model here
// keeps the env var and permissions in sync.
const BEDROCK_INFERENCE_PROFILE_ID = 'us.anthropic.claude-sonnet-4-6'
// Underlying foundation-model id (the profile id without its "us." prefix).
const BEDROCK_FOUNDATION_MODEL_ID = BEDROCK_INFERENCE_PROFILE_ID.replace(/^us\./, '')
// Regions the "us." profile can route to.
const BEDROCK_PROFILE_REGIONS = ['us-east-1', 'us-east-2', 'us-west-2']

export interface BackendProps {
  vpc: ec2.Vpc
  albSecurityGroup: ec2.SecurityGroup
  serviceSecurityGroup: ec2.SecurityGroup
  userPool: cognito.IUserPool
}

/**
 * ECS Fargate service running the WebSocket server, behind an internet-facing
 * ALB. The ALB only forwards requests carrying the CloudFront secret header;
 * everything else gets 403. The task role is least-privilege (Bedrock/Polly/
 * Transcribe only). Cognito config is injected so the server verifies JWTs.
 *
 * A construct (not a stack) so it shares a stack with the CloudFront front
 * door and the Cognito app client; see AppStack for why.
 */
export class Backend extends Construct {
  public readonly loadBalancer: elbv2.ApplicationLoadBalancer
  public readonly originVerifySecret: secretsmanager.Secret
  /** The server container, so AppStack can inject the Cognito app client ID. */
  public readonly container: ecs.ContainerDefinition

  constructor(scope: Construct, id: string, props: BackendProps) {
    super(scope, id)

    const { vpc, albSecurityGroup, serviceSecurityGroup, userPool } = props
    const { region, account } = cdk.Stack.of(this)

    // Secret value CloudFront will send in a header; the ALB rule requires it.
    this.originVerifySecret = new secretsmanager.Secret(this, 'OriginVerifySecret', {
      description: 'Shared secret so only CloudFront can reach the ALB',
      generateSecretString: {
        excludePunctuation: true,
        passwordLength: 40,
      },
    })
    cdk.Validations.of(this.originVerifySecret).acknowledge({
      id: 'AwsSolutions-SMG4',
      reason:
        'Resolved at deploy time into both the ALB rule and the CloudFront origin header; automatic rotation would break the match until both are redeployed, so it is rotated manually (replace + redeploy) if needed.',
    })

    const cluster = new ecs.Cluster(this, 'Cluster', {
      vpc,
      containerInsightsV2: ecs.ContainerInsights.ENABLED,
    })

    // Least-privilege task role.
    const taskRole = new iam.Role(this, 'TaskRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      description: 'Polly Avatar server task role (least privilege)',
    })
    taskRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ['polly:SynthesizeSpeech', 'polly:DescribeVoices'],
        resources: ['*'],
      })
    )
    taskRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ['transcribe:StartStreamTranscription', 'transcribe:StartStreamTranscriptionWebSocket'],
        resources: ['*'],
      })
    )
    taskRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
        // The "us." model id is a CROSS-REGION inference profile that routes to
        // multiple US regions. The invoke is authorized against the profile ARN
        // in this region AND the underlying foundation-model ARN in whichever
        // region it lands. Scoped to this one model: the trailing "*" only
        // covers version suffixes of the same model id.
        resources: [
          `arn:aws:bedrock:${region}:${account}:inference-profile/${BEDROCK_INFERENCE_PROFILE_ID}`,
          ...BEDROCK_PROFILE_REGIONS.map(
            (r) => `arn:aws:bedrock:${r}::foundation-model/${BEDROCK_FOUNDATION_MODEL_ID}*`
          ),
        ],
      })
    )
    // Reviewed cdk-nag findings: the wildcards the services require.
    cdk.Validations.of(taskRole).acknowledge(
      {
        id: 'AwsSolutions-IAM5[Resource::*]',
        reason:
          'Polly SynthesizeSpeech/DescribeVoices and Transcribe streaming support no resource-level permissions, so Resource "*" is required.',
      },
      ...BEDROCK_PROFILE_REGIONS.map((r) => ({
        id: `AwsSolutions-IAM5[Resource::arn:aws:bedrock:${r}::foundation-model/${BEDROCK_FOUNDATION_MODEL_ID}*]`,
        reason:
          'Scoped to the one model the app uses; the trailing "*" only covers that model id\'s version suffix in a region the cross-region inference profile routes to.',
      }))
    )

    const taskDef = new ecs.FargateTaskDefinition(this, 'TaskDef', {
      cpu: 512,
      memoryLimitMiB: 1024,
      taskRole,
      // Run on ARM64 (Graviton): cheaper, and matches the image which is pinned
      // to linux/arm64 below. The image asset is force-built for arm64 even on
      // x86 hosts, so build + runtime architecture can never drift (a mismatch
      // crashes the container with exit 255 and no logs).
      runtimePlatform: {
        cpuArchitecture: ecs.CpuArchitecture.ARM64,
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
      },
    })
    // Applies to the task definition and its CDK-generated execution role.
    cdk.Validations.of(taskDef).acknowledge(
      {
        id: 'AwsSolutions-ECS2',
        reason:
          'Container env vars are non-secret config (port, region, Cognito pool/client IDs, Hosted UI domain, model id). No secrets are passed via env.',
      },
      {
        id: 'AwsSolutions-IAM5[Resource::*]',
        reason: 'CDK-generated ECS execution role: ecr:GetAuthorizationToken requires Resource "*".',
      }
    )

    const logGroup = new logs.LogGroup(this, 'LogGroup', {
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    })

    this.container = taskDef.addContainer('Server', {
      image: ecs.ContainerImage.fromAsset(REPO_ROOT, {
        file: 'server/Dockerfile',
        // Always build an arm64 image to match the Graviton runtime above,
        // even if built on an x86 host/CI. Keeps build + runtime in sync.
        platform: ecrAssets.Platform.LINUX_ARM64,
        // Bust the OS-package-upgrade layer each day so rebuilds pull the
        // latest security patches (openssl, etc.) instead of a stale cached
        // layer. Date-granularity keeps the CDK asset hash stable within a day
        // (avoids needless rebuilds) while guaranteeing daily freshness.
        buildArgs: {
          CACHE_BUST: new Date().toISOString().slice(0, 10),
        },
      }),
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: 'server', logGroup }),
      environment: {
        PORT: '8080',
        AWS_REGION: region,
        AUTH_ENABLED: 'true', // fail-closed in the cloud
        COGNITO_USER_POOL_ID: userPool.userPoolId,
        // COGNITO_CLIENT_ID is added by AppStack once the app client exists.
        BEDROCK_MODEL_ID: BEDROCK_INFERENCE_PROFILE_ID,
        POLLY_ENGINE: 'neural',
        // The container runs as a non-root user with a root-owned working dir,
        // so the default ./.sessions path isn't writable. Point the persistent
        // conversation store at /tmp, which is writable in the task.
        SESSION_STORE_DIR: '/tmp/polly-avatar-sessions',
      },
      portMappings: [{ containerPort: 8080 }],
    })

    const service = new ecs.FargateService(this, 'Service', {
      cluster,
      taskDefinition: taskDef,
      desiredCount: 1,
      minHealthyPercent: 100, // keep the single task serving during deploys
      maxHealthyPercent: 200,
      securityGroups: [serviceSecurityGroup],
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      assignPublicIp: false,
      // Roll back automatically if a new deployment's tasks fail to stabilize.
      circuitBreaker: { rollback: true },
    })

    // Internet-facing ALB (locked to CloudFront via SG + secret header).
    this.loadBalancer = new elbv2.ApplicationLoadBalancer(this, 'Alb', {
      vpc,
      internetFacing: true,
      securityGroup: albSecurityGroup,
      // Drop headers with invalid field names instead of forwarding them.
      dropInvalidHeaderFields: true,
    })

    // ALB access logs. ALB log delivery only supports SSE-S3 (not KMS).
    // Short retention keeps cost negligible for a demo. RETAIN with no
    // autoDeleteObjects: emptying a bucket on delete needs a CDK helper Lambda,
    // and this app has none. Left behind on destroy; logs expire after 30 days.
    const albLogBucket = new s3.Bucket(this, 'AlbLogBucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      versioned: true,
      lifecycleRules: [{ expiration: cdk.Duration.days(30), noncurrentVersionExpiration: cdk.Duration.days(1) }],
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    })
    this.loadBalancer.logAccessLogs(albLogBucket, 'alb')
    // Resource-scoped scanner exemptions: logging a log bucket would recurse.
    const albLogCfn = albLogBucket.node.defaultChild as s3.CfnBucket
    albLogCfn.addMetadata('checkov', {
      skip: [{ id: 'CKV_AWS_18', comment: 'This is the access-log destination bucket itself.' }],
    })
    albLogCfn.addMetadata('guard', { SuppressedRules: ['S3_BUCKET_LOGGING_ENABLED'] })
    cdk.Validations.of(albLogBucket).acknowledge({
      id: 'AwsSolutions-S1',
      reason: 'This is the access-log destination bucket itself; logging it would recurse.',
    })
    albLogCfn.addMetadata('cfn_nag', {
      rules_to_suppress: [{ id: 'W35', reason: 'This is the access-log destination bucket itself.' }],
    })

    const listener = this.loadBalancer.addListener('HttpListener', {
      port: 80,
      open: false,
      // Default: reject anything that doesn't match the secret-header rule.
      defaultAction: elbv2.ListenerAction.fixedResponse(403, {
        contentType: 'text/plain',
        messageBody: 'Forbidden',
      }),
    })

    const targetGroup = new elbv2.ApplicationTargetGroup(this, 'Tg', {
      vpc,
      port: 8080,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      targets: [service],
      healthCheck: {
        path: '/health',
        interval: cdk.Duration.seconds(30),
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 3,
      },
      // WebSocket connections are long-lived.
      stickinessCookieDuration: cdk.Duration.hours(1),
      deregistrationDelay: cdk.Duration.seconds(30),
    })

    // Only forward requests carrying the correct CloudFront secret header.
    listener.addAction('ForwardIfVerified', {
      priority: 10,
      conditions: [
        elbv2.ListenerCondition.httpHeader('X-Origin-Verify', [
          this.originVerifySecret.secretValue.unsafeUnwrap(),
        ]),
      ],
      action: elbv2.ListenerAction.forward([targetGroup]),
    })
  }
}
