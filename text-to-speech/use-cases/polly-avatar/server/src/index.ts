import { createServer, IncomingMessage } from 'http'
import { WebSocketServer, WebSocket } from 'ws'
import { handleConnection } from './services/sessionHandler.js'
import { verifyToken, extractToken, isAuthEnabled } from './services/authService.js'
import { handleConfigRequest } from './services/runtimeConfig.js'

const PORT = parseInt(process.env.PORT || '8080', 10)

// HTTP server handles the ALB health check, the browser's /config.json
// (Cognito settings), and hosts the WebSocket upgrade.
const httpServer = createServer((req, res) => {
  if (req.url === '/health' || req.url === '/healthz') {
    res.writeHead(200, { 'Content-Type': 'text/plain' })
    res.end('ok')
    return
  }
  if (handleConfigRequest(req, res)) return
  res.writeHead(404)
  res.end()
})

// noServer mode so we can authenticate before accepting the upgrade.
const wss = new WebSocketServer({ noServer: true })

httpServer.on('upgrade', async (req: IncomingMessage, socket, head) => {
  // Only handle WebSocket upgrades on the /ws path (and root for local dev).
  const path = (req.url ?? '').split('?')[0]
  if (path !== '/ws' && path !== '/') {
    socket.destroy()
    return
  }

  // Authenticate the connection (env-gated; no-op locally).
  const token = extractToken(req.url)
  const ok = await verifyToken(token)
  if (!ok) {
    console.warn('[Server] Rejected unauthenticated WebSocket upgrade')
    socket.write('HTTP/1.1 401 Unauthorized\r\n\r\n')
    socket.destroy()
    return
  }

  wss.handleUpgrade(req, socket, head, (ws) => {
    wss.emit('connection', ws, req)
  })
})

wss.on('connection', (ws: WebSocket) => {
  console.log('[Server] Client connected')
  handleConnection(ws)
  ws.on('close', () => {
    console.log('[Server] Client disconnected')
  })
})

httpServer.listen(PORT, () => {
  console.log(`[Server] Listening on :${PORT} (auth ${isAuthEnabled() ? 'ENABLED' : 'disabled'})`)
})
