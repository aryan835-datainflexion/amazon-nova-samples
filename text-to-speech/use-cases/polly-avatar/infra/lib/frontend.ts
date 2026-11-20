import * as cdk from 'aws-cdk-lib'
import { Construct } from 'constructs'
import * as s3 from 'aws-cdk-lib/aws-s3'
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront'
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins'
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2'
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager'
import * as wafv2 from 'aws-cdk-lib/aws-wafv2'
import * as ec2 from 'aws-cdk-lib/aws-ec2'

export interface FrontendProps {
  loadBalancer: elbv2.ApplicationLoadBalancer
  originVerifySecret: secretsmanager.Secret
}

/**
 * The single front door. CloudFront serves the SPA from a private S3 bucket
 * (OAC) and routes /ws (WebSocket) and /config.json (Cognito settings) to the
 * ALB, injecting the X-Origin-Verify secret header so the ALB only accepts
 * CloudFront traffic. A WAF web ACL rate-limits abuse.
 *
 * The site bucket starts empty. The built client is uploaded manually with
 * `aws s3 sync` (see infra/README.md), so the app needs no upload Lambda.
 */
export class Frontend extends Construct {
  public readonly siteBucket: s3.Bucket
  public readonly distribution: cloudfront.Distribution
  /** https://<distribution domain>, the app's public URL. */
  public readonly appUrl: string

  constructor(scope: Construct, id: string, props: FrontendProps) {
    super(scope, id)

    const { loadBalancer, originVerifySecret } = props

    // Access logs for the site bucket (S3 server access logs) and CloudFront
    // (standard logs). CloudFront writes via ACLs, so ACLs must be enabled
    // (BUCKET_OWNER_PREFERRED keeps the bucket owner as owner of delivered
    // objects). RETAIN with no autoDeleteObjects: emptying a bucket on delete
    // needs a CDK helper Lambda, and this app has none. Left behind on
    // destroy; logs expire after 30 days.
    const logBucket = new s3.Bucket(this, 'AccessLogBucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      versioned: true,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,
      lifecycleRules: [{ expiration: cdk.Duration.days(30), noncurrentVersionExpiration: cdk.Duration.days(1) }],
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    })
    // Resource-scoped scanner exemptions: logging a log bucket would recurse.
    const logBucketCfn = logBucket.node.defaultChild as s3.CfnBucket
    logBucketCfn.addMetadata('checkov', {
      skip: [{ id: 'CKV_AWS_18', comment: 'This is the access-log destination bucket itself.' }],
    })
    logBucketCfn.addMetadata('guard', { SuppressedRules: ['S3_BUCKET_LOGGING_ENABLED'] })
    logBucketCfn.addMetadata('cfn_nag', {
      rules_to_suppress: [{ id: 'W35', reason: 'This is the access-log destination bucket itself.' }],
    })

    // Private bucket for the built SPA. No public access; only CloudFront (OAC).
    // Filled manually with `aws s3 sync` after deploy. RETAIN for the same
    // reason as the log bucket (and because a non-empty bucket would otherwise
    // block `cdk destroy`). Versioned so a bad upload can be rolled back.
    this.siteBucket = new s3.Bucket(this, 'SiteBucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      versioned: true,
      // Old SPA builds are only needed briefly for rollback.
      lifecycleRules: [{ noncurrentVersionExpiration: cdk.Duration.days(7) }],
      serverAccessLogsBucket: logBucket,
      serverAccessLogsPrefix: 's3-site/',
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    })

    // WAF: rate limit to protect the expensive AI backend from abuse.
    const webAcl = new wafv2.CfnWebACL(this, 'WebAcl', {
      defaultAction: { allow: {} },
      scope: 'CLOUDFRONT',
      visibilityConfig: {
        cloudWatchMetricsEnabled: true,
        metricName: 'PollyAvatarWebAcl',
        sampledRequestsEnabled: true,
      },
      rules: [
        {
          name: 'RateLimit',
          priority: 1,
          action: { block: {} },
          statement: {
            rateBasedStatement: { limit: 1000, aggregateKeyType: 'IP' },
          },
          visibilityConfig: {
            cloudWatchMetricsEnabled: true,
            metricName: 'RateLimit',
            sampledRequestsEnabled: true,
          },
        },
        {
          name: 'CommonRuleSet',
          priority: 2,
          overrideAction: { none: {} },
          statement: {
            managedRuleGroupStatement: {
              vendorName: 'AWS',
              name: 'AWSManagedRulesCommonRuleSet',
              // WebSocket upgrade requests (and some clients) legitimately omit
              // the User-Agent header, which NoUserAgent_HEADER blocks — that
              // was rejecting our /ws connections. Set it to count (allow).
              ruleActionOverrides: [
                {
                  name: 'NoUserAgent_HEADER',
                  actionToUse: { count: {} },
                },
              ],
            },
          },
          visibilityConfig: {
            cloudWatchMetricsEnabled: true,
            metricName: 'CommonRuleSet',
            sampledRequestsEnabled: true,
          },
        },
        {
          // Blocks known-malicious request patterns, incl. Log4j (CVE-2021-44228).
          name: 'KnownBadInputsRuleSet',
          priority: 3,
          overrideAction: { none: {} },
          statement: {
            managedRuleGroupStatement: {
              vendorName: 'AWS',
              name: 'AWSManagedRulesKnownBadInputsRuleSet',
            },
          },
          visibilityConfig: {
            cloudWatchMetricsEnabled: true,
            metricName: 'KnownBadInputsRuleSet',
            sampledRequestsEnabled: true,
          },
        },
      ],
    })

    // Header CloudFront adds to every origin request to the ALB.
    const originVerifyPolicy = new cloudfront.OriginRequestPolicy(this, 'WsOriginReqPolicy', {
      // CloudFront handles the WebSocket Upgrade/Connection headers itself and
      // rejects them in an allowlist. We only need the Sec-WebSocket-* headers
      // plus the query string (which carries the auth token).
      headerBehavior: cloudfront.OriginRequestHeaderBehavior.allowList(
        'Sec-WebSocket-Key',
        'Sec-WebSocket-Version',
        'Sec-WebSocket-Protocol',
        'Sec-WebSocket-Extensions'
      ),
      queryStringBehavior: cloudfront.OriginRequestQueryStringBehavior.all(),
      cookieBehavior: cloudfront.OriginRequestCookieBehavior.none(),
    })

    const albOrigin = new origins.HttpOrigin(loadBalancer.loadBalancerDnsName, {
      protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
      httpPort: 80,
      customHeaders: {
        'X-Origin-Verify': originVerifySecret.secretValue.unsafeUnwrap(),
      },
      // Keep-alive for long-lived WS.
      readTimeout: cdk.Duration.seconds(60),
      keepaliveTimeout: cdk.Duration.seconds(60),
    })

    const s3Origin = origins.S3BucketOrigin.withOriginAccessControl(this.siteBucket)

    // SPA route rewrite: for the S3 (static) behavior only, rewrite extension-
    // less paths to /index.html so client-side routes work. (A distribution-wide
    // errorResponses mapping would also swallow the ALB's /ws responses.)
    const spaRewriteFn = new cloudfront.Function(this, 'SpaRewrite', {
      code: cloudfront.FunctionCode.fromInline(`
function handler(event) {
  var req = event.request;
  var uri = req.uri;
  // If the path has no file extension, serve the SPA entry point.
  if (!uri.includes('.')) {
    req.uri = '/index.html';
  }
  return req;
}
`),
    })

    this.distribution = new cloudfront.Distribution(this, 'Distribution', {
      defaultRootObject: 'index.html',
      webAclId: webAcl.attrArn,
      defaultBehavior: {
        origin: s3Origin,
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
        functionAssociations: [
          {
            function: spaRewriteFn,
            eventType: cloudfront.FunctionEventType.VIEWER_REQUEST,
          },
        ],
      },
      additionalBehaviors: {
        // Cognito settings for the browser, generated by the server from its
        // environment so they always match the deployed stack. Never cached.
        '/config.json': {
          origin: albOrigin,
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
        },
        // WebSocket path -> ALB. No caching; responses pass through untouched
        // so the WS upgrade works.
        '/ws': {
          origin: albOrigin,
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy: originVerifyPolicy,
        },
      },
      priceClass: cloudfront.PriceClass.PRICE_CLASS_100,
      enableLogging: true,
      logBucket,
      logFilePrefix: 'cloudfront/',
      minimumProtocolVersion: cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
    })
    // Reviewed cdk-nag findings: no custom domain / ACM certificate (demo decision).
    cdk.Validations.of(this.distribution).acknowledge(
      {
        id: 'AwsSolutions-CFR1',
        reason: 'Demo is meant to be usable from any region; access is gated by Cognito and WAF rate limiting.',
      },
      {
        id: 'AwsSolutions-CFR4',
        reason:
          'Uses the default *.cloudfront.net certificate, whose viewer TLS policy is fixed by CloudFront; TLSv1.2-only needs a custom domain + ACM certificate, which this demo omits.',
      },
      {
        id: 'AwsSolutions-CFR5',
        reason:
          'CloudFront-to-ALB is HTTP: the ALB has no certificate without a custom domain. The ALB accepts only CloudFront origin IPs carrying the X-Origin-Verify secret; viewers always use HTTPS.',
      }
    )

    // Restrict the ALB security group to CloudFront's origin-facing IPs.
    const cfPrefixList = ec2.PrefixList.fromLookup(this, 'CfPrefixList', {
      prefixListName: 'com.amazonaws.global.cloudfront.origin-facing',
    })
    loadBalancer.connections.allowFrom(
      ec2.Peer.prefixList(cfPrefixList.prefixListId),
      ec2.Port.tcp(80),
      'Allow inbound only from CloudFront'
    )

    this.appUrl = `https://${this.distribution.distributionDomainName}`
  }
}
