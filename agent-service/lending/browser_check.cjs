// Host browser verification against an isolated SQL Server test schema.
const assert = require('node:assert/strict');
const { createServer } = require('node:http');
const { once } = require('node:events');
const { readFile, mkdir } = require('node:fs/promises');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { randomBytes } = require('node:crypto');

async function main() {
  const [checkout, output, chrome, minimumText = '12'] = process.argv.slice(2);
  const minimum = Number(minimumText);
  assert.ok([8, 12].includes(minimum));
  const password = 'a😀' + 'b'.repeat(minimum - 2);
  const { chromium } = require(path.resolve(__dirname, '../runtime/lending/browser-tools/node_modules/playwright-core'));
  const { createApp } = await import(pathToFileURL(path.join(checkout, 'backend/app.js')));
  await mkdir(output, { recursive: true });
  const { connectDatabase, migrate, seedDemo, sqlServerStore } =
    await import(pathToFileURL(path.join(checkout, 'backend/database.js')));
  const { pool, sql } = await connectDatabase();
  const schema = 'lending_browser_' + randomBytes(8).toString('hex');
  let created = false;
  const query = statement => pool.request().query(statement);
  const count = async () => (await query(
    `SELECT COUNT(*) AS total FROM [${schema}].[users] WHERE username LIKE 'browser.%'`
  )).recordset[0].total;
  let handler;
  const files = new Map([
    ['/', ['index.html', 'text/html']],
    ['/app.js', ['app.js', 'text/javascript']],
    ['/styles.css', ['styles.css', 'text/css']],
  ]);
  const server = createServer(async (req, res) => {
    const file = files.get(req.url);
    if (!file) return handler(req, res);
    try {
      const body = await readFile(path.join(checkout, 'frontend', file[0]));
      res.writeHead(200, { 'Content-Type': file[1] }).end(body);
    } catch {
      res.writeHead(500).end();
    }
  });
  let browser;
  try {
    assert.equal((await query('SELECT DB_NAME() AS name')).recordset[0].name, 'ClubEquipmentLending_Test');
    await query(`CREATE SCHEMA [${schema}]`);
    created = true;
    await migrate(pool, sql, schema);
    await seedDemo(pool, sql, {
      LENDING_ENV: 'test', DEMO_MEMBER_PASSWORD: 'Synthetic-member-123',
      DEMO_MANAGER_PASSWORD: 'Synthetic-manager-123',
    }, schema);
    const store = sqlServerStore(pool, sql, schema);
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const origin = 'http://localhost:' + server.address().port;
    handler = await createApp({ store, origin });
    browser = await chromium.launch({ executablePath: chrome, headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(origin);
    await page.locator('#open-register').click();
    await page.locator('#register-submit').click();
    assert.equal(await count(), 0);
    await page.locator('#register-name').fill('browser.member');
    await page.locator('#register-password').fill(password.slice(0, -1));
    await page.locator('#register-submit').click();
    await page.waitForFunction(() => document.querySelector('#register-password-error').textContent.length > 0);
    assert.equal(await count(), 0);
    const validationMessage = await page.locator('#register-password-error').innerText();
    assert.match(validationMessage, new RegExp(String(minimum)));
    await page.screenshot({ path: path.join(output, 'short-password-error.png'), fullPage: true });
    await page.locator('#register-password').fill(password);
    await page.locator('#register-submit').click();
    await page.locator('#register-success').waitFor({ state: 'visible' });
    assert.equal((await store.userByUsername('browser.member')).role, 'MEMBER');
    assert.equal((await context.cookies()).length, 0);
    await page.screenshot({ path: path.join(output, 'registered.png'), fullPage: true });
    await page.locator('#register-success a').click();
    assert.equal(await page.locator('#password').inputValue(), '');
    await page.locator('#password').fill(password);
    await page.locator('#login-form button[type=submit]').click();
    await page.locator('#assets').waitFor({ state: 'visible' });
    assert.match(await page.locator('#assets').innerText(), /DEMO-01/);
    await page.screenshot({ path: path.join(output, 'catalog.png'), fullPage: true });
    await page.locator('#logout').click();
    await page.locator('#open-register').click();
    await page.locator('#register-name').fill('browser.member');
    await page.locator('#register-password').fill(password);
    await page.locator('#register-submit').click();
    await page.waitForFunction(() => document.querySelector('#register-name-error').textContent.length > 0);
    assert.equal(await count(), 1);
    await page.route('**/auth/register', route => route.abort());
    await page.locator('#register-name').fill('browser.recovery');
    await page.locator('#register-submit').click();
    await page.waitForFunction(() => document.querySelector('#register-error').textContent.length > 0);
    await page.unroute('**/auth/register');
    await page.locator('#register-submit').click();
    await page.locator('#register-success').waitFor({ state: 'visible' });
    assert.equal(await count(), 2);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({
      passed: true, store: 'SQL Server isolated test schema, synthetic data', minimum,
      passwordBoundary: {
        rejectedCodePoints: [...password.slice(0, -1)].length,
        acceptedCodePoints: [...password].length, includesEmoji: true,
        validationMessage, correctedInSamePageAndSession: true,
        noAccountCreatedForRejectedInput: true,
      },
      checks: ['empty input', 'short Unicode password error then correction to exact minimum in same form',
        'registration', 'MEMBER role', 'no auto-login cookie',
        'manual login', 'catalog', 'duplicate username', 'network failure and retry', 'no page errors'],
      screenshots: ['short-password-error.png', 'registered.png', 'catalog.png'],
    }));
  } finally {
    if (browser) await browser.close();
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    try {
      if (created) {
        for (const table of ['loan_events', 'loan_requests', 'sessions', 'equipment', 'users']) {
          await query(`DROP TABLE IF EXISTS [${schema}].[${table}]`);
        }
        await query(`DROP SCHEMA [${schema}]`);
      }
    } finally {
      await pool.close();
    }
  }
}
main().catch(error => { console.error(error.stack); process.exitCode = 1; });
