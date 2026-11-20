import { CognitoJwtVerifier } from 'aws-jwt-verify'

/**
 * Env-gated Cognito JWT verification for WebSocket connections.
 *
 * Fail-closed: auth is ENFORCED unless AUTH_ENABLED is explicitly "false".
 * A misconfigured cloud deploy therefore rejects connections rather than
 * allowing anonymous access. Local dev opts out with AUTH_ENABLED=false.
 */
const AUTH_ENABLED = process.env.AUTH_ENABLED !== 'false'

// Lazily build the verifier so local dev (auth disabled) needs no Cognito config.
let verifier: ReturnType<typeof CognitoJwtVerifier.create> | null = null

function getVerifier() {
  if (verifier) return verifier
  const userPoolId = process.env.COGNITO_USER_POOL_ID
  const clientId = process.env.COGNITO_CLIENT_ID
  if (!userPoolId || !clientId) {
    throw new Error('COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID must be set when AUTH_ENABLED')
  }
  verifier = CognitoJwtVerifier.create({
    userPoolId,
    clientId,
    tokenUse: 'id', // the ID token identifies the user
  })
  return verifier
}

export function isAuthEnabled(): boolean {
  return AUTH_ENABLED
}

/**
 * Verifies the token from a WebSocket connection. Returns true when auth is
 * disabled (local dev) or the token is valid; false otherwise.
 */
export async function verifyToken(token: string | undefined): Promise<boolean> {
  if (!AUTH_ENABLED) return true
  if (!token) return false
  try {
    await getVerifier().verify(token)
    return true
  } catch (err) {
    console.warn('[Auth] Token verification failed:', err instanceof Error ? err.message : err)
    return false
  }
}

/** Extracts the token from the WebSocket upgrade request URL (?token=...). */
export function extractToken(requestUrl: string | undefined): string | undefined {
  if (!requestUrl) return undefined
  try {
    const url = new URL(requestUrl, 'http://localhost')
    return url.searchParams.get('token') ?? undefined
  } catch {
    return undefined
  }
}
