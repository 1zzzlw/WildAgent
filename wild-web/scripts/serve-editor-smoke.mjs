import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'
const root = fileURLToPath(new URL('..', import.meta.url))
const server = await createServer({
  root,
  server: { host: '127.0.0.1', port: 5178, strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:18080' }, '/ws': { target: 'ws://127.0.0.1:18080', ws: true } } },
})
await server.listen()
server.printUrls()
