import type { IncomingMessage, ServerResponse } from 'http'
import { isAuthEnabled } from './authService.js'

/**
 * Serves /config.json: the Cognito settings the browser needs to sign in.
 *
 * The client itself is static files in S3, uploaded manually with `aws s3 sync`
 * (see infra/README.md). CloudFront routes just this one path to the ALB, so
 * the settings always match the deployed stack and nobody has to write or
 * upload a config file by hand. Values are public identifiers, not secrets.
 */
function runtimeConfig(): { status: number; body: unknown } {
  const authEnabled = isAuthEnabled()
  const cognito = {
    userPoolId: process.env.COGNITO_USER_POOL_ID ?? '',
    clientId: process.env.COGNITO_CLIENT_ID ?? '',
    domain: process.env.COGNITO_DOMAIN ?? '',
    region: process.env.AWS_REGION ?? '',
  }
  if (authEnabled && Object.values(cognito).some((v) => v === '')) {
    // Fail loudly rather than send the browser to a broken login URL.
    console.error('[Config] Auth is enabled but Cognito settings are incomplete')
    return { status: 500, body: { error: 'Server misconfigured' } }
  }
  return { status: 200, body: { authEnabled, cognito } }
}

/** Handles GET/HEAD /config.json. Returns false for any other request. */
export function handleConfigRequest(req: IncomingMessage, res: ServerResponse): boolean {
  const path = (req.url ?? '').split('?')[0]
  if (path !== '/config.json' || (req.method !== 'GET' && req.method !== 'HEAD')) return false

  const { status, body } = runtimeConfig()
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-cache',
    'X-Content-Type-Options': 'nosniff',
  })
  res.end(req.method === 'HEAD' ? undefined : JSON.stringify(body))
  return true
}
