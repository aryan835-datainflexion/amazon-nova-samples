import * as cdk from 'aws-cdk-lib'
import { AwsSolutionsChecks } from 'cdk-nag'
import { AppStack } from '../lib/app-stack.js'

const app = new cdk.App()

// cdk-nag (AWS Solutions rules) runs on every synth/deploy and FAILS it on any
// finding that isn't acknowledged in code with a reason
// (`Validations.of(construct).acknowledge(...)`, next to the resource).
// writeSuppressionsToCloudFormation copies each acknowledgment into the
// template's `cdk_nag` metadata as an audit trail.
cdk.Validations.of(app).addPlugins(
  new AwsSolutionsChecks(app, { verbose: true, writeSuppressionsToCloudFormation: true })
)

// CloudFront + WAF web ACL for CloudFront must be in us-east-1. Keep the whole
// app there for simplicity (also where Bedrock/Polly access is configured).
const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION || 'us-east-1',
}

// The whole demo is one stack (network, Cognito, backend, frontend); see AppStack.
new AppStack(app, 'PollyAvatar', { env })

app.synth()
