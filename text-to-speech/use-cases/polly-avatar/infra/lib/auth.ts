import * as cdk from 'aws-cdk-lib'
import { Construct } from 'constructs'
import * as cognito from 'aws-cdk-lib/aws-cognito'

/**
 * Cognito user pool for authenticating access to the app.
 *
 * Invite-only: self sign-up is disabled, so an admin creates users. Uses the
 * Hosted UI (OAuth authorization code flow). The app client is created in
 * AppStack, next to the CloudFront distribution whose URL it registers as a
 * callback. To federate with an external IdP (e.g. corporate SSO) later, add an
 * identity provider here and list it on the client in AppStack.
 *
 * A construct inside the single PollyAvatar stack. The pool is deleted with the
 * stack (users included): fine for a demo, and it leaves nothing behind.
 */
export class Auth extends Construct {
  public readonly userPool: cognito.UserPool
  public readonly userPoolDomain: cognito.UserPoolDomain

  constructor(scope: Construct, id: string) {
    super(scope, id)

    this.userPool = new cognito.UserPool(this, 'UserPool', {
      userPoolName: 'polly-avatar-users',
      selfSignUpEnabled: false, // invite-only
      signInAliases: { email: true },
      autoVerify: { email: true },
      standardAttributes: {
        email: { required: true, mutable: true },
      },
      passwordPolicy: {
        minLength: 12,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      mfa: cognito.Mfa.OPTIONAL,
      mfaSecondFactor: { sms: false, otp: true },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // demo: users go with the stack
    })
    // Reviewed cdk-nag findings (accepted for this demo).
    cdk.Validations.of(this.userPool).acknowledge(
      {
        id: 'AwsSolutions-COG2',
        reason: 'MFA is OPTIONAL (TOTP available) to keep demo sign-in simple. Invite-only pool with a strong password policy.',
      },
      {
        id: 'AwsSolutions-COG8',
        reason: 'Cognito Plus feature plan (threat protection) is a paid tier; not used for an invite-only demo pool.',
      }
    )

    // Hosted UI domain. Must be globally unique; include the account id.
    this.userPoolDomain = this.userPool.addDomain('HostedUiDomain', {
      cognitoDomain: {
        domainPrefix: `polly-avatar-${cdk.Stack.of(this).account}`,
      },
    })

    // No users are created here. The pool is invite-only: an admin adds users
    // after deploy (Cognito console or `aws cognito-idp admin-create-user`; see
    // infra/README.md "Creating users"). Keeping credentials out of the stack
    // means no password ever appears in the CloudFormation template or outputs.
  }
}
