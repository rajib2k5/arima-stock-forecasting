/**
 * A static file server for the built app (app/dist), on a port the OS picks, so the screenshot tool
 * never needs vite and never touches another server's port. Node built-ins only.
 */
import { createReadStream } from 'node:fs'
import { stat } from 'node:fs/promises'
import { createServer } from 'node:http'
import { extname, join, normalize, sep } from 'node:path'

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
}

/** A port another server owns (the owner's vite dev server): refused even if the OS offered it. */
export const RESERVED_PORTS = [5179]

/** Serves `root` on 127.0.0.1 at a free port; resolves to { url, close }. */
export async function serve(root) {
  const server = createServer(async (req, res) => {
    const path = decodeURIComponent(new URL(req.url ?? '/', 'http://localhost').pathname)
    const file = normalize(join(root, path === '/' ? 'index.html' : path))
    // Nothing outside the served folder, whatever the path says.
    if (file !== root && !file.startsWith(root.endsWith(sep) ? root : root + sep)) {
      res.writeHead(403).end()
      return
    }
    try {
      if (!(await stat(file)).isFile()) throw new Error('not a file')
      res.writeHead(200, { 'content-type': TYPES[extname(file)] ?? 'application/octet-stream', 'cache-control': 'no-store' })
      createReadStream(file).pipe(res)
    } catch {
      res.writeHead(404).end()
    }
  })
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const { port } = server.address()
  if (RESERVED_PORTS.includes(port)) {
    server.close()
    throw new Error(`the OS offered port ${port}, which belongs to another server`)
  }
  return { url: `http://127.0.0.1:${port}/`, close: () => new Promise((resolve) => server.close(resolve)) }
}
