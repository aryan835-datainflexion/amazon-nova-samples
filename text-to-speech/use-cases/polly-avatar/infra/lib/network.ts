import * as cdk from 'aws-cdk-lib'
import { Construct } from 'constructs'
import * as ec2 from 'aws-cdk-lib/aws-ec2'
import * as logs from 'aws-cdk-lib/aws-logs'

/**
 * Networking for the app: a VPC with private subnets for the Fargate service,
 * VPC interface endpoints so calls to Bedrock/Polly/Transcribe never leave AWS
 * (no NAT needed), and security groups wiring ALB -> service.
 *
 * A construct inside the single PollyAvatar stack (see app-stack.ts).
 */
export class Network extends Construct {
  public readonly vpc: ec2.Vpc
  public readonly albSecurityGroup: ec2.SecurityGroup
  public readonly serviceSecurityGroup: ec2.SecurityGroup

  constructor(scope: Construct, id: string) {
    super(scope, id)
    const { region } = cdk.Stack.of(this)

    // Private-with-egress subnets, but we avoid NAT by using VPC endpoints for
    // the AWS services the task calls. Public subnets host only the ALB.
    this.vpc = new ec2.Vpc(this, 'Vpc', {
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        // Only the ALB lives in the public subnets and it gets its own public
        // addresses, so nothing needs auto-assigned public IPs.
        { name: 'public', subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24, mapPublicIpOnLaunch: false },
        { name: 'private', subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
    })

    // VPC flow logs (all traffic) to CloudWatch Logs, short retention for a demo.
    const flowLogGroup = new logs.LogGroup(this, 'FlowLogGroup', {
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    })
    this.vpc.addFlowLog('FlowLog', {
      destination: ec2.FlowLogDestination.toCloudWatchLogs(flowLogGroup),
      trafficType: ec2.FlowLogTrafficType.ALL,
    })

    // Security group for the ALB. Inbound is locked to CloudFront at the
    // Frontend construct (AppStack) via the managed prefix list; here we just create it.
    this.albSecurityGroup = new ec2.SecurityGroup(this, 'AlbSg', {
      vpc: this.vpc,
      description: 'ALB security group (inbound restricted to CloudFront)',
      // No blanket egress. The only egress the ALB needs (to the service on
      // 8080, for traffic + health checks) is added by CDK when the target
      // group registers the Fargate service (Backend construct), plus the explicit
      // rule below.
      allowAllOutbound: false,
    })

    // Security group for the Fargate service. Only the ALB may reach it.
    this.serviceSecurityGroup = new ec2.SecurityGroup(this, 'ServiceSg', {
      vpc: this.vpc,
      description: 'Fargate service SG (inbound only from ALB)',
      allowAllOutbound: true,
    })
    this.serviceSecurityGroup.addIngressRule(
      this.albSecurityGroup,
      ec2.Port.tcp(8080),
      'Allow inbound from ALB to app port'
    )
    this.albSecurityGroup.addEgressRule(
      this.serviceSecurityGroup,
      ec2.Port.tcp(8080),
      'Allow outbound from ALB to app port'
    )

    // Interface endpoints so the isolated task can reach AWS services without
    // NAT/internet. Bedrock runtime, Polly, Transcribe streaming.
    const endpointSg = new ec2.SecurityGroup(this, 'EndpointSg', {
      vpc: this.vpc,
      description: 'VPC endpoint SG',
      // Interface endpoints only answer inbound requests; they never initiate.
      allowAllOutbound: false,
    })
    endpointSg.addIngressRule(
      this.serviceSecurityGroup,
      ec2.Port.tcp(443),
      'HTTPS from service to endpoints'
    )

    const addEndpoint = (name: string, service: ec2.InterfaceVpcEndpointAwsService) => {
      this.vpc.addInterfaceEndpoint(name, {
        service,
        securityGroups: [endpointSg],
        subnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
        privateDnsEnabled: true,
        // Don't add CDK's default "allow 443 from the whole VPC CIDR" rule; the
        // explicit service-SG rule above is the only caller that needs access.
        open: false,
      })
    }

    addEndpoint('BedrockRuntimeEndpoint', ec2.InterfaceVpcEndpointAwsService.BEDROCK_RUNTIME)
    addEndpoint('PollyEndpoint', ec2.InterfaceVpcEndpointAwsService.POLLY)
    addEndpoint('TranscribeStreamingEndpoint', ec2.InterfaceVpcEndpointAwsService.TRANSCRIBE_STREAMING)
    // STS so the SDK can resolve task-role credentials without internet.
    addEndpoint('StsEndpoint', ec2.InterfaceVpcEndpointAwsService.STS)

    // Cognito IDP so the server can fetch the JWKS to verify Cognito JWTs on
    // the WebSocket upgrade (aws-jwt-verify hits cognito-idp's .well-known).
    // No built-in AwsService constant, so use the raw service name with private
    // DNS enabled (so cognito-idp.<region>.amazonaws.com resolves to it).
    new ec2.InterfaceVpcEndpoint(this, 'CognitoIdpEndpoint', {
      vpc: this.vpc,
      service: new ec2.InterfaceVpcEndpointService(
        `com.amazonaws.${region}.cognito-idp`,
        443
      ),
      securityGroups: [endpointSg],
      subnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      privateDnsEnabled: true,
      open: false, // see addEndpoint above
      // The cognito-idp endpoint isn't offered in every AZ; let CDK query which
      // AZs support it and place the endpoint only there.
      lookupSupportedAzs: true,
    })
    // CloudWatch Logs so the task can ship logs without NAT.
    addEndpoint('CloudWatchLogsEndpoint', ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS)
    // ECR + S3 gateway so Fargate can pull the container image without NAT.
    addEndpoint('EcrEndpoint', ec2.InterfaceVpcEndpointAwsService.ECR)
    addEndpoint('EcrDockerEndpoint', ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER)
    this.vpc.addGatewayEndpoint('S3Endpoint', {
      service: ec2.GatewayVpcEndpointAwsService.S3,
    })
  }
}
