import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';

export async function serve(t, app) {
  const server = createServer(app);
  t.after(() => new Promise((resolve) => server.close(resolve)));
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return (path, options) => fetch('http://127.0.0.1:' + server.address().port + path, options);
}

export const origin = 'https://lending.example.test';
export const register = (request, input, headers = {}) => request('/auth/register', {
  method: 'POST',
  headers: { Origin: origin, 'Content-Type': 'application/json', ...headers },
  body: JSON.stringify(input),
});
export const login = (request, username, password, site = origin) => request('/auth/login', {
  method: 'POST',
  headers: { Origin: site, 'Content-Type': 'application/json' },
  body: JSON.stringify({ username, password }),
});
export const cookie = (response) => response.headers.get('set-cookie').split(';')[0];

export async function expectError(response, status, code) {
  assert.equal(response.status, status);
  assert.deepEqual(await response.json(), { code });
}
