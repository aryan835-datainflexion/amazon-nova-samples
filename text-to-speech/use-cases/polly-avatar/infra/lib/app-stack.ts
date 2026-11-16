import * as cdk from 'aws-cdk-lib'
import { Construct } from 'constructs'
import * as cognito from 'aws-cdk-lib/aws-cognito'
import { Network } from './network.js'
import { Auth } from './auth.js'
import { Backend } from './backend.js'
import { Frontend } from './frontend.js'

// Local Vite dev server, kept as an allowed redirect so a developer can sign in
// against the deployed pool from `npm run dev` if they enable auth locally.
const LOCAL_DEV_URL = 'http://localhost:5173'

/**
 * The whole demo in ONE stack: network, Cognito, backend, frontend. No
 * cross-stack exports/imports, so nothing can block a delete or update, and a
 * single `cdk deploy` produces a working app. CloudFormation orders it all:
 *
 *   VPC (Network) -> ALB + Fargate (Backend) -> CloudFront (Frontend)
 *     -> app client (callback = CloudFront URL)
 *     -> server env (client ID, Hosted UI domain)
 *
 * The SPA is static files in S3, uploaded manually with `aws s3 sync` after
 * deploy (infra/README.md), so the stack has no upload Lambda; it contains no
 * Lambda functions at all. The browser's Cognito settings come from
 * /config.json, which CloudFront routes to the server (generated from its env).
 */
export class AppStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props)

    const network = new Network(this, 'Network')
    const { userPool, userPoolDomain } = new Auth(this, 'Auth')

    const backend = new Backend(this, 'Backend', {
      vpc: network.vpc,
      albSecurityGroup: network.albSecurityGroup,
      serviceSecurityGroup: network.serviceSecurityGroup,
      userPool,
    })

    const frontend = new Frontend(this, 'Frontend', {
      loadBalancer: backend.loadBalancer,
      originVerifySecret: backend.originVerifySecret,
    })

    // Public SPA client. Created after the distribution so its callback URLs
    // reference it directly; no post-deploy patching.
    const client = new cognito.UserPoolClient(this, 'WebClient', {
      userPool,
      userPoolClientName: 'polly-avatar-web',
      generateSecret: false, // public SPA client, no secret
      authFlows: { userSrp: true },
      oAuth: {
        flows: { authorizationCodeGrant: true },
        scopes: [cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
        callbackUrls: [frontend.appUrl, LOCAL_DEV_URL],
        logoutUrls: [frontend.appUrl, LOCAL_DEV_URL],
      },
      supportedIdentityProviders: [cognito.UserPoolClientIdentityProvider.COGNITO],
      preventUserExistenceErrors: true,
      accessTokenValidity: cdk.Duration.hours(1),
      idTokenValidity: cdk.Duration.hours(1),
      refreshTokenValidity: cdk.Duration.days(30),
    })

    // The server verifies the JWT audience against this client, and serves
    // both values (with the pool ID and region) to the browser as /config.json
    // (CloudFront routes that one path to the ALB).
    backend.container.addEnvironment('COGNITO_CLIENT_ID', client.userPoolClientId)
    backend.container.addEnvironment('COGNITO_DOMAIN', userPoolDomain.baseUrl())

    new cdk.CfnOutput(this, 'AppUrl', {
      value: frontend.appUrl,
      description: 'Open this to use the app (create a Cognito user first).',
    })
    new cdk.CfnOutput(this, 'UserPoolId', {
      value: userPool.userPoolId,
      description: 'Use with `aws cognito-idp admin-create-user --user-pool-id`.',
    })
    new cdk.CfnOutput(this, 'UserPoolClientId', { value: client.userPoolClientId })
    new cdk.CfnOutput(this, 'HostedUiDomain', { value: userPoolDomain.baseUrl() })
    // Used by the manual frontend upload (aws s3 sync + invalidation).
    new cdk.CfnOutput(this, 'SiteBucketName', { value: frontend.siteBucket.bucketName })
    new cdk.CfnOutput(this, 'DistributionId', { value: frontend.distribution.distributionId })
    new cdk.CfnOutput(this, 'AlbDnsName', { value: backend.loadBalancer.loadBalancerDnsName })
  }
}
