import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { Login } from './components/Login'
import { useAuth } from './hooks/useAuth'
import { loadRuntimeConfig } from './config'

function Root() {
  const { ready, authenticated, idToken, login, logout } = useAuth()

  // Wait for auth to initialize (checking session / handling redirect).
  if (!ready) {
    return <div style={loadingStyle}>Loading…</div>
  }

  // Auth-gated: show the login screen until authenticated. Local dev (auth
  // disabled) reports authenticated immediately, so App renders straight away.
  if (!authenticated) {
    return <Login onLogin={login} />
  }

  return <App authToken={idToken} onLogout={logout} />
}

const loadingStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  height: '100vh',
  color: '#888',
  background: '#1a1a2e',
}

const root = ReactDOM.createRoot(document.getElementById('root')!)

// Load the deploy-time /config.json (Cognito settings) before anything reads
// `config`, then render. See config.ts.
loadRuntimeConfig()
  .then(() => {
    root.render(
      <React.StrictMode>
        <Root />
      </React.StrictMode>
    )
  })
  .catch((err: unknown) => {
    console.error(err)
    root.render(
      <div style={loadingStyle} role="alert">
        Configuration unavailable. Please redeploy the app.
      </div>
    )
  })
