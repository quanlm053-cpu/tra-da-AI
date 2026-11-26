import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const [checkout, revision] = process.argv.slice(2);
const load = name => import(pathToFileURL(path.join(checkout, 'backend', name)));
const { createApp } = await load('app.js');
const { connectDatabase, migrate, seedDemo, sqlServerStore } = await load('database.js');
const { pool, sql } = await connectDatabase();
await migrate(pool, sql);
await seedDemo(pool, sql, {
  LENDING_ENV: 'demo', DEMO_MEMBER_PASSWORD: 'DemoMember-3102',
  DEMO_MANAGER_PASSWORD: 'DemoManager-3102',
});
const origin = 'http://localhost:3102';
const app = await createApp({ store: sqlServerStore(pool, sql), origin });
const files = new Map([
  ['/', ['index.html', 'text/html']], ['/app.js', ['app.js', 'text/javascript']],
  ['/styles.css', ['styles.css', 'text/css']],
]);
const refresh = `<script>
setInterval(async () => {
  try {
    const response = await fetch('/__preview_version', {cache: 'no-store'});
    if (response.ok && (await response.json()).revision !== ${JSON.stringify(revision)}) location.reload();
  } catch {}
}, 10000);
</script>`;
createServer(async (req, res) => {
  if (req.headers.host !== 'localhost:3102') return res.writeHead(421).end();
  const pathname = new URL(req.url, origin).pathname;
  res.setHeader('Cache-Control', 'no-store');
  if (pathname === '/__preview_version') {
    return res.writeHead(200, {'Content-Type': 'application/json'}).end(JSON.stringify({revision}));
  }
  const file = req.method === 'GET' && files.get(pathname);
  if (!file) return app(req, res);
  try {
    let body = await readFile(path.join(checkout, 'dist', file[0]));
    if (file[0] === 'index.html') body = Buffer.from(body.toString().replace('</body>', refresh + '</body>'));
    res.writeHead(200, {'Content-Type': file[1] + '; charset=utf-8'}).end(body);
  } catch {
    res.writeHead(404).end();
  }
}).listen(3102, '127.0.0.1', () => console.log('Preview ' + revision + ' ' + origin));
