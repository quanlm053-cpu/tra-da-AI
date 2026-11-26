import { createServer } from 'node:http';
import { createApp } from './app.js';
import { connectDatabase, migrate, sqlServerStore, seedDemo } from './database.js';

const command = process.argv[2] ?? 'start';
if (!['start', 'migrate', 'seed'].includes(command)) throw new Error('Unknown command');
const { pool, sql } = await connectDatabase();

if (command !== 'start') {
  try {
    if (command === 'migrate') await migrate(pool, sql);
    else await seedDemo(pool, sql, process.env);
  } finally {
    await pool.close();
  }
} else {
  const origin = new URL(process.env.APP_ORIGIN);
  if (origin.protocol !== 'https:' || origin.origin !== process.env.APP_ORIGIN) {
    throw new Error('APP_ORIGIN must be the public HTTPS origin, without a trailing slash');
  }
  const store = sqlServerStore(pool, sql);
  await store.deleteExpiredSessions();
  const server = createServer(await createApp({
    store,
    origin: origin.origin,
    trustedProxyIp: '127.0.0.1',
  }));
  const cleanup = setInterval(() => {
    store.deleteExpiredSessions().catch((error) => console.error('Session cleanup failed', error.code ?? error.name));
  }, 60 * 60 * 1000);
  cleanup.unref();
  pool.on('error', (error) => console.error('Idle database connection failed', error.code ?? error.name));
  server.listen(Number(process.env.PORT ?? 3000), process.env.HOST ?? '127.0.0.1');
  for (const signal of ['SIGINT', 'SIGTERM']) {
    process.once(signal, () => {
      clearInterval(cleanup);
      server.close(() => void pool.close());
    });
  }
}
