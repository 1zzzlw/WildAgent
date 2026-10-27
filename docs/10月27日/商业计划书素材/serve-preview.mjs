import { createServer } from '../../../wild-web/node_modules/vite/dist/node/index.js'
import { fileURLToPath } from 'node:url'

const root=fileURLToPath(new URL('../../../wild-web',import.meta.url))
const server=await createServer({
  root,
  cacheDir:'node_modules/.vite-business-plan',
  server:{host:'127.0.0.1',port:5187,strictPort:true,proxy:{'/api':{target:'http://127.0.0.1:18080'},'/ws':{target:'ws://127.0.0.1:18080',ws:true}}},
})
await server.listen()
server.printUrls()
