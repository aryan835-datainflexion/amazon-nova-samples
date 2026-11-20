import { useState, useEffect, useCallback } from 'react'
import { config } from '../config'

/**
 * Lightweight Cognito Hosted UI auth (OAuth2 implicit-style via token endpoint
 * is avoided; we use the Authorization Code flow with the Hosted UI).
 *
 * When auth is disabled (local dev), this reports authenticated immediately
 * with no token, so the app renders normally.
 *
 * Flow when enabled:
 *  1. No session -> redirect to Cognito Hosted UI login.
 *  2. Cognito redirects back with ?code=... -> exchange for tokens.
 *  3. Store the ID token (used to authenticate the WebSocket).
 */

interface AuthState {
  ready: boolean // finished initializing
  authenticated: boolean
  idToken: string | null
  email: string | null
}

const STORAGE_KEY = 'polly_auth_tokens'

interface StoredTokens {
  idToken: string
  accessToken: string
  expiresAt: number // epoch ms
}

function loadTokens(): StoredTokens | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const t = JSON.parse(raw) as StoredTokens
    if (t.expiresAt <= Date.now()) return null // expired
    return t
  } catch {
    return null
  }
}

function decodeJwt(token: string): Record<string, unknown> | null {
  try {
    const payload = token.split('.')[1]
    return JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
  } catch {
    return null
  }
}

function hostedUiUrl(kind: 'login' | 'logout'): string {
  const { domain, clientId, redirectUri } = config.cognito
  const params = new URLSearchParams({
    client_id: clientId,
    response_type: 'code',
    scope: 'openid email profile',
    redirect_uri: redirectUri,
  })
  if (kind === 'login') return `${domain}/login?${params.toString()}`
  const logoutParams = new URLSearchParams({
    client_id: clientId,
    logout_uri: redirectUri,
  })
  return `${domain}/logout?${logoutParams.toString()}`
}

async function exchangeCodeForTokens(code: string): Promise<StoredTokens | null> {
  const { domain, clientId, redirectUri } = config.cognito
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: clientId,
    code,
    redirect_uri: redirectUri,
  })
  try {
    const resp = await fetch(`${domain}/oauth2/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    })
    if (!resp.ok) return null
    const data = await resp.json()
    return {
      idToken: data.id_token,
      accessToken: data.access_token,
      expiresAt: Date.now() + (data.expires_in ?? 3600) * 1000,
    }
  } catch {
    return null
  }
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    ready: !config.authEnabled, // when disabled, ready immediately
    authenticated: !config.authEnabled,
    idToken: null,
    email: null,
  })

  useEffect(() => {
    if (!config.authEnabled) return

    ;(async () => {
      // Returning from Hosted UI with an auth code?
      const url = new URL(window.location.href)
      const code = url.searchParams.get('code')
      if (code) {
        const tokens = await exchangeCodeForTokens(code)
        if (tokens) {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens))
          // Clean the code from the URL.
          window.history.replaceState({}, '', window.location.pathname)
          const claims = decodeJwt(tokens.idToken)
          setState({
            ready: true,
            authenticated: true,
            idToken: tokens.idToken,
            email: (claims?.email as string) ?? null,
          })
          return
        }
      }

      // Existing valid session?
      const existing = loadTokens()
      if (existing) {
        const claims = decodeJwt(existing.idToken)
        setState({
          ready: true,
          authenticated: true,
          idToken: existing.idToken,
          email: (claims?.email as string) ?? null,
        })
        return
      }

      setState({ ready: true, authenticated: false, idToken: null, email: null })
    })()
  }, [])

  const login = useCallback(() => {
    window.location.href = hostedUiUrl('login')
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    if (config.authEnabled) {
      window.location.href = hostedUiUrl('logout')
    } else {
      setState({ ready: true, authenticated: false, idToken: null, email: null })
    }
  }, [])

  return { ...state, login, logout }
}
