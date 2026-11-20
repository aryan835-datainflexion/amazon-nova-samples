/**
 * Environment-aware client configuration.
 *
 * Local dev: talks to the standalone WebSocket server on :8080, auth disabled.
 * Cloud: connects through CloudFront at wss://<host>/ws with auth enabled. The
 * Cognito settings come from /config.json, which CloudFront routes to the
 * server and the server generates from its environment
 * (server/src/services/runtimeConfig.ts), so the same build works in any
 * account (no rebuild per deploy).
 *
 * Precedence: /config.json (if served) > VITE_* build-time env > defaults.
 * Call loadRuntimeConfig() once before rendering.
 */

export const config = {
  authEnabled: import.meta.env.VITE_AUTH_ENABLED === 'true',

  cognito: {
    userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID ?? '',
    clientId: import.meta.env.VITE_COGNITO_CLIENT_ID ?? '',
    // Hosted UI domain, e.g. https://polly-avatar.auth.us-east-1.amazoncognito.com
    domain: import.meta.env.VITE_COGNITO_DOMAIN ?? '',
    // Where Cognito redirects back after login. The app is served from the
    // registered callback URL, so the current origin is always correct.
    redirectUri: import.meta.env.VITE_COGNITO_REDIRECT_URI ?? window.location.origin,
    region: import.meta.env.VITE_AWS_REGION ?? 'us-east-1',
  },
}

/** Shape of /config.json (see server/src/services/runtimeConfig.ts). */
interface RuntimeConfig {
  authEnabled: boolean
  cognito: { userPoolId: string; clientId: string; domain: string; region: string }
}

function isRuntimeConfig(value: unknown): value is RuntimeConfig {
  const v = value as RuntimeConfig | null
  return (
    typeof v === 'object' &&
    v !== null &&
    typeof v.authEnabled === 'boolean' &&
    typeof v.cognito === 'object' &&
    v.cognito !== null &&
    ['userPoolId', 'clientId', 'domain', 'region'].every(
      (k) => typeof (v.cognito as Record<string, unknown>)[k] === 'string'
    )
  )
}

/**
 * Loads /config.json when the deployment provides one. Absent in local dev:
 * Vite answers unknown paths with index.html, so anything that isn't JSON is
 * treated as "no runtime config" and the build-time values stand.
 *
 * Throws when served over HTTPS (i.e. deployed) without any auth config, so a
 * broken deployment shows an error instead of an app that can't connect.
 */
export async function loadRuntimeConfig(): Promise<void> {
  let runtime: unknown = null
  try {
    const res = await fetch('/config.json', { cache: 'no-store' })
    const isJson = (res.headers.get('content-type') ?? '').includes('application/json')
    if (res.ok && isJson) runtime = await res.json()
  } catch {
    // Network error: fall through to build-time values.
  }

  if (isRuntimeConfig(runtime)) {
    config.authEnabled = runtime.authEnabled
    config.cognito = { ...runtime.cognito, redirectUri: window.location.origin }
    return
  }

  if (window.location.protocol === 'https:' && !config.authEnabled) {
    throw new Error('Missing /config.json: this deployment has no authentication settings.')
  }
}

/**
 * Builds the WebSocket URL for the current environment.
 * - Explicit override via VITE_WS_URL (useful for custom setups).
 * - Cloud (served over https): same host, /ws path, through CloudFront.
 * - Local dev (http): the standalone server on :8080.
 */
export function getWebSocketUrl(token?: string): string {
  const explicit = import.meta.env.VITE_WS_URL as string | undefined
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'

  let base: string
  if (explicit) {
    base = explicit
  } else if (window.location.protocol === 'https:') {
    // Cloud: routed through CloudFront on the /ws path.
    base = `${proto}//${window.location.host}/ws`
  } else {
    // Local dev: standalone server.
    base = `${proto}//${window.location.hostname}:8080`
  }

  // Browsers can't set headers on a WebSocket, so the JWT is passed as a query
  // param and validated by the server on the upgrade.
  if (token) {
    const sep = base.includes('?') ? '&' : '?'
    return `${base}${sep}token=${encodeURIComponent(token)}`
  }
  return base
}
