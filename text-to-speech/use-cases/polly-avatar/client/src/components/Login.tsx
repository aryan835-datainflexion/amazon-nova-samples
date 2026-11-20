interface LoginProps {
  onLogin: () => void
}

export function Login({ onLogin }: LoginProps) {
  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>Polly Avatar Demo</h1>
        <p style={styles.subtitle}>Please sign in to continue</p>
        <button style={styles.button} onClick={onLogin}>
          Sign in
        </button>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100vh',
    background: '#1a1a2e',
  },
  card: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '16px',
    padding: '40px 48px',
    borderRadius: '12px',
    background: 'rgba(30, 30, 54, 0.9)',
    border: '1px solid #2a2a4a',
  },
  title: {
    fontSize: '1.4rem',
    fontWeight: 600,
    color: '#e0e0ff',
  },
  subtitle: {
    fontSize: '0.9rem',
    color: '#888',
  },
  button: {
    marginTop: '8px',
    padding: '10px 32px',
    borderRadius: '8px',
    border: 'none',
    background: 'linear-gradient(135deg, #6a6aff, #4a4adf)',
    color: '#fff',
    fontSize: '0.95rem',
    fontWeight: 500,
    cursor: 'pointer',
  },
}
