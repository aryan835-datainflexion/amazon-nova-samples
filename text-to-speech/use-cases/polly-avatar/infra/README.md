# Polly Avatar — Infrastructure (CDK)

Deploys the app to AWS behind CloudFront with Cognito auth and a locked-down
backend. Local development is unaffected and needs none of this.

> **Sample code, not production-ready.** Read
> [Deployment security and non-production notice](#deployment-security-and-non-production-notice)
> before deploying.

## Architecture

```
Browser (Cognito login) → CloudFront (WAF) ─┬─ S3 (private, OAC)        static SPA
                                            ├─ /config.json → ALB → Fargate   Cognito settings
                                            └─ /ws          → ALB → Fargate   WebSocket
                                                    (private subnets, VPC endpoints
                                                     for Bedrock / Polly / Transcribe)
```

- **CloudFront** is the single front door. Direct S3 access is blocked (OAC);
  direct ALB access is blocked (CloudFront-IP security group + `X-Origin-Verify`
  secret header rule).
- **The SPA is static files in S3**, uploaded by you with `aws s3 sync` after
  the infrastructure deploy (see "Upload the frontend"). The browser gets its
  Cognito settings from `/config.json`, which CloudFront routes to the server,
  generated from the task's environment, so they always match the stack.
- **No Lambda functions.** CDK's usual S3 upload helper is a Lambda, so the
  upload is a manual step instead. The site and log buckets are retained rather
  than emptied on delete for the same reason (see "Tear down").
- **Cognito** user pool (invite-only, Hosted UI) gates the app. The server
  verifies the JWT on the WebSocket upgrade (fail-closed).
- **Fargate** task runs in private isolated subnets; reaches AWS services via
  VPC interface endpoints (no NAT, no internet egress).
- **WAF** rate-limits requests to protect the paid AI backend from abuse.
- **Task role** is least-privilege: Polly, Transcribe streaming, Bedrock invoke.


## Stack

The whole demo is **one CloudFormation stack, `PollyAvatar`**, built from four
constructs:

| Construct | Contents |
|-----------|----------|
| `lib/network.ts` | VPC, subnets, security groups, VPC endpoints, flow logs |
| `lib/auth.ts` | Cognito user pool + Hosted UI domain (no users; you add them) |
| `lib/backend.ts` | ECS Fargate + ALB, task role, origin-verify secret, ALB log bucket |
| `lib/frontend.ts` | CloudFront + WAF, S3 site bucket, access-log bucket |

`lib/app-stack.ts` wires them together and adds the Cognito app client. With
a single stack there are no cross-stack exports, so nothing can block an
update or delete, and CloudFormation orders everything in one deploy: the app
client registers the distribution's URL as its callback, and the server
receives the client ID (to verify tokens) and serves it to the browser in
`/config.json`. The client build has no environment-specific values, so the
same build works in any account.

## Deployment security and non-production notice

> **This is sample code for demonstration. It is not production-ready.** Review
> it against your own security, compliance, availability and cost requirements
> before using it with real users or data. You are responsible for what you
> deploy and for the charges it incurs.

**What the sample does for security**
- Sign-in through an invite-only Cognito user pool. The server verifies the
  JWT on every WebSocket connection and refuses it otherwise (fail-closed).
- No users or passwords are created or stored by the deployment.
- WAF on CloudFront: rate limiting plus the AWS common and known-bad-inputs
  managed rule sets.
- The ALB accepts only CloudFront's IP ranges plus a secret header, and the
  Fargate task runs in isolated subnets that reach AWS only through VPC
  endpoints.
- The task role is limited to Polly, Transcribe streaming and one Bedrock model.
- Access logs (ALB, CloudFront, S3) and VPC flow logs are on. cdk-nag checks
  every synth and deploy.

**Known limitations you should understand before deploying**
- **No end-to-end TLS.** Viewers use HTTPS to CloudFront, but CloudFront to the
  ALB, and the ALB to the container, use plain HTTP. The ALB is internet-facing
  and has no certificate because the sample uses no custom domain. The
  `X-Origin-Verify` header and the WebSocket `?token=` JWT cross the public
  internet unencrypted on the first of those hops.
- **AWS-managed encryption keys only.** No customer-managed KMS keys.
- **MFA is optional** and Cognito's Plus feature plan is not enabled.
- **Single task, single region, no autoscaling.** Conversation history lives on
  the task's ephemeral disk and is lost when the task restarts.
- **Conversation content** is sent to Amazon Transcribe, Bedrock and Polly. The
  server's own logs hold only metadata (voice, language, character counts,
  errors), never what is said, but you remain responsible for how your
  account's AWS service logging and data-handling settings apply to it.
- **The app is on the public internet.** Anyone with the URL reaches the login
  page. Create only the users you trust, and run `npm run destroy` when you're
  done.
- **Retained resources:** three S3 buckets stay behind after destroy (see
  "Tear down").

**Before any production use**, at minimum: add a custom domain with an ACM
certificate and require HTTPS to the origin, use customer-managed keys where
your policy requires them, require MFA, run more than one task across
availability zones, and re-run the security scans against your own account.

## Prerequisites (one-time)

- **Node.js 20+**.
- A **container runtime** — [Finch](https://runfinch.com/) or Docker — running
  locally (CDK builds the server image during deploy).
- **AWS credentials** for the target account, with permission to create the
  resources above and to call Amazon Polly, Transcribe, and Bedrock.
- **Amazon Bedrock model access** enabled for the configured model
  (`us.anthropic.claude-sonnet-4-6`) in the account/region.
- A **one-time CDK bootstrap** of the account/region (from `infra/`):
  `npm ci && npx cdk bootstrap`.

## Deploy (from your local machine)

Deploy your own copy from a local checkout. No git or pipeline required. Two
steps: deploy the infrastructure, then upload the frontend.

### 1. Deploy the infrastructure

```bash
cd infra
npm run deploy
```

This builds the server container image and deploys the `PollyAvatar` stack in
one pass. cdk-nag checks it first (see "Security checks"). When it finishes, the
outputs include **`AppUrl`** (open this after step 2), **`SiteBucketName`** and
**`DistributionId`** (for step 2), and **`UserPoolId`** (for creating users,
below).

CDK builds the server container with Docker by default. **Using Finch?** Start
its VM and point CDK at it first:

```bash
finch vm start            # or `finch vm init` the first time
export CDK_DOCKER=finch
```

Deploys to the region of your AWS credentials/profile (default `us-east-1`).
The CloudFront WAF web ACL must live in `us-east-1`, so the whole app is kept
there for simplicity. For another region, set `CDK_DEFAULT_REGION` and make
sure Bedrock model access is enabled there.

### 2. Upload the frontend

List the stack outputs and copy `SiteBucketName` and `DistributionId`:

```bash
aws cloudformation describe-stacks --stack-name PollyAvatar --query "Stacks[0].Outputs[].{OutputKey:OutputKey,OutputValue:OutputValue}" --output table
```

They're also printed at the end of `npm run deploy`, and shown in the
CloudFormation console under the `PollyAvatar` stack's **Outputs** tab.

Then build the client, upload it, and refresh CloudFront's cache. Replace
`<SiteBucketName>` and `<DistributionId>` with your values:

```bash
cd ../client          # from infra/, where step 1 left you
npm ci
npm run build
aws s3 sync dist s3://<SiteBucketName> --delete
aws cloudfront create-invalidation --distribution-id <DistributionId> --paths "/*"
```

`--delete` removes files left over from older builds. The invalidation makes
CloudFront serve the new files right away instead of cached ones.

Repeat step 2 whenever you change the client. Server or infrastructure
changes only need step 1. The client build contains no account-specific
values: CloudFront routes `/config.json` to the server, which returns the
Cognito settings for this deployment.

## Creating users (required before first sign-in)

The deploy does **not** create any users, so no credentials ever appear in the
CloudFormation template or stack outputs. The pool is invite-only (self sign-up
is disabled), so add each user yourself, either way:

**Cognito console:** User pools → `polly-avatar-users` → Users → Create user.
Enter the email address, mark it verified, and choose to send an email
invitation (or set a temporary password yourself).

**AWS CLI:**

```bash
aws cognito-idp admin-create-user \
  --user-pool-id <UserPoolId> \
  --username you@example.com \
  --user-attributes Name=email,Value=you@example.com Name=email_verified,Value=true
```

`<UserPoolId>` is the `UserPoolId` stack output, printed at the end of
`npm run deploy`. Cognito emails a temporary password to that address, so
use a real mailbox. Then open the App URL, sign in, and set your own password
when prompted (the account starts in "force change password" state).

The password policy requires at least 12 characters with lowercase, uppercase,
digits, and symbols. See the
[admin-create-user reference](https://docs.aws.amazon.com/cli/latest/reference/cognito-idp/admin-create-user.html).

### Upgrading a deployment made with `deploy.sh` (one-time)

Earlier versions deployed four stacks (`PollyAvatar-Network`, `-Auth`,
`-Backend`, `-Frontend`). This version replaces them with the single
`PollyAvatar` stack, so delete the old ones first. The Hosted UI domain name
(`polly-avatar-<account>`) is reused and must be released before the new
stack can claim it. Delete in dependency order:

```bash
for s in PollyAvatar-Frontend PollyAvatar-Backend PollyAvatar-Auth PollyAvatar-Network; do
  aws cloudformation delete-stack --stack-name "$s"
  aws cloudformation wait stack-delete-complete --stack-name "$s"
done
cd infra && npm run deploy
```

Then upload the frontend (step 2 of "Deploy") and create users as above. You
get a **new App URL**. The old version retained its user pool on delete, so an
orphaned `polly-avatar-users` pool (with the old users) is left behind; delete
it from the Cognito console.

### Security checks (cdk-nag)

[cdk-nag](https://github.com/cdklabs/cdk-nag) (AWS Solutions rules) runs inside
the CDK app on every `cdk synth` and `cdk deploy`, and **fails the command** on
any finding that hasn't been reviewed. Reviewed, accepted findings are
acknowledged in code next to the resource, with a reason:

```ts
cdk.Validations.of(resource).acknowledge({ id: 'AwsSolutions-XYZ1', reason: 'Why this is acceptable' })
```

Fix the finding where you can. Acknowledge it only when it's a deliberate
choice. Each acknowledgment is also written to the template's `cdk_nag`
metadata as an audit trail.

### Architecture note (important)

The server image is **pinned to `linux/arm64`** and Fargate runs on **Graviton
(ARM64)**. This matches Apple-silicon dev machines and is cheaper. Because the
image platform is pinned, it builds arm64 correctly even on an x86 host — build
and runtime can't drift (a mismatch crashes the task with exit 255 and no logs).

### OS package security patches

The server Dockerfile runs `apk update && apk upgrade` in both stages, so every
build pulls the latest OS package versions (e.g. openssl security fixes) rather
than whatever shipped in the base image. A daily `CACHE_BUST` build arg (set by
the CDK image asset) forces that upgrade layer to re-run, so cached layers can't
leave the image on stale/vulnerable packages. Net effect: a `cdk deploy` on any
new day rebuilds with current patches automatically. To force an immediate
re-patch the same day, change the CACHE_BUST granularity in `lib/backend.ts`
(e.g. include the time) or deploy with `--no-cache` on the asset build.

## Tear down

```bash
cd infra
npm run destroy
```

Deletes the `PollyAvatar` stack and stops the recurring charges (Fargate, ALB,
VPC endpoints, CloudFront). The Cognito user pool is deleted too, **including
its users** (fine for a demo; create them again after a redeploy).

**Left behind on purpose: three S3 buckets**, the site bucket (your uploaded
frontend) and two access-log buckets (S3/CloudFront and ALB). Emptying a bucket
during stack delete requires a CDK helper Lambda function, and this app
deliberately has no Lambdas; a non-empty bucket would otherwise block
`npm run destroy`. Logs expire after 30 days, and the site files are a few
hundred MB at most, so the cost is a few cents a month. To remove them:

```bash
# Find the three buckets (CloudFormation-generated names):
aws s3api list-buckets --output text \
  --query "Buckets[?starts_with(Name, 'pollyavatar-')].Name"
```

The buckets are versioned, so empty them in the **S3 console** (select the
bucket → **Empty**, which also removes old versions), then **Delete**.

## Local dev is unchanged

Local runs with `AUTH_ENABLED=false` (server) and `VITE_AUTH_ENABLED` unset
(client) — no login, no Cognito. It uses your local AWS credentials (see the
[AWS CLI configuration guide](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html)).
Just `npm run dev` in `server/` and `client/` as before.

## Cost notes (demo scale, us-east-1, approx/month)

- Fargate task (0.5 vCPU / 1 GB, always on): ~$15–20
- ALB: ~$16 base + traffic
- VPC interface endpoints: ~$7 each × 6 ≈ $42 (or switch to a single NAT for less)
- CloudFront / WAF / Cognito / S3: pennies at demo traffic
- Bedrock / Polly / Transcribe: pay-per-use (the real variable cost)

To cut cost, scale the Fargate service to 0 when idle, or replace VPC endpoints
with a single NAT gateway.

## Switching to corporate SSO (later)

The user pool uses native Cognito auth. To federate to an external IdP (SAML/
OIDC), add an identity provider in `lib/auth.ts`, add it to the client's
`supportedIdentityProviders`, and point the Hosted UI at it. The client and
server auth code doesn't change — it already speaks standard OAuth/JWT.
