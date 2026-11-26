const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const { runInNewContext } = require('node:vm');

const source = readFileSync(require.resolve('../app.js'), 'utf8')
  .replace(/void checkSession\(\);\s*$/, '');
const manager = { id: 1, role: 'MANAGER', csrf_token: 'demo-token' };
const pending = { id: 42, status: 'PENDING' };

function setup({ session = { ...manager }, hash = '#equipment' } = {}) {
  const nodes = new Map();
  const requests = [];
  const windowListeners = {};
  const location = { hash };
  function element(id) {
    return {
      id,
      children: [],
      dataset: {},
      listeners: {},
      addEventListener(type, listener) { this.listeners[type] = listener; },
      click() { if (!this.disabled) this.listeners.click?.(); },
      append(...children) { this.children.push(...children); },
      close() {},
      contains() { return false; },
      focus() {},
      replaceChildren(...children) { this.children = children; },
      reset() {},
      showModal() { this.open = true; },
      removeAttribute() {},
      setAttribute() {},
      classList: { toggle() {} },
    };
  }
  const app = runInNewContext(source + `
    user = initialSession;
    ({ byId, checkSession, logout, submitDecision, managementBusy, managementDecisions, getUser: () => user,
      openManagement(hash, role = 'MANAGER') {
        user.role = role;
        location.hash = hash;
        showManagement();
      },
      showApprovedDetail(item) {
        managementView = { id: item.id, approved: true, items: [item] };
        renderManagement(managementView);
      } });
  `, {
    initialSession: session,
    document: {
      createElement: element,
      getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, element(id));
        return nodes.get(id);
      },
      querySelectorAll: () => [],
    },
    window: { addEventListener(type, listener) { windowListeners[type] = listener; } },
    location,
    history: { replaceState(_state, _title, newHash) { location.hash = newHash; } },
    AbortController,
    AbortSignal,
    TextEncoder,
    clearTimeout,
    fetch(path, options) {
      if (path === '/equipment') return Promise.resolve(Response.json([]));
      const { promise, resolve, reject } = Promise.withResolvers();
      requests.push({ path, method: options.method ?? 'GET', headers: options.headers, body: options.body, resolve, reject });
      return promise;
    },
  });
  return {
    ...app,
    nodes,
    navigate(newHash = location.hash) {
      location.hash = newHash;
      windowListeners.hashchange();
    },
    take(path, method = 'GET') {
      const request = requests.shift();
      assert.equal(request?.path, path);
      assert.equal(request.method, method);
      return request;
    },
    requests,
  };
}

const flush = () => new Promise(setImmediate);

test('registration validates Unicode and allows manual member login after success', async () => {
  const app = setup({ session: null, hash: '#register' });
  app.navigate();
  app.byId('register-name').value = 'demo.member176';
  const password = app.byId('register-password');
  const submit = app.nodes.get('register-form').listeners.submit;
  const event = { preventDefault() {} };

  for (const [value, message] of [
    ['', /Vui lòng nhập mật khẩu/],
    [' '.repeat(8), /ký tự khác khoảng trắng/],
    ['abc1234\uD800', /Unicode không hợp lệ/],
    ['abc123😀', /^Mật khẩu phải có ít nhất 8 ký tự$/],
    ['😀'.repeat(256) + 'a', /vượt quá 1\.024 byte/],
  ]) {
    password.value = value;
    await submit(event);
    assert.match(app.nodes.get('register-password-error').textContent, message);
    assert.equal(app.requests.length, 0);
  }

  password.value = '😀'.repeat(256);
  const boundarySubmission = submit(event);
  const boundaryRequest = app.take('/auth/register', 'POST');
  assert.equal(JSON.parse(boundaryRequest.body).password, password.value);
  boundaryRequest.resolve(Response.json({ code: 'INVALID_INPUT' }, { status: 400 }));
  await boundarySubmission;

  password.value = ' abc12😀 ';
  const submission = submit(event);
  const request = app.take('/auth/register', 'POST');
  assert.deepEqual(JSON.parse(request.body), { username: 'demo.member176', password: ' abc12😀 ' });
  assert.equal(app.nodes.get('register-submit').disabled, true);
  request.resolve(Response.json({ username: 'demo.member176' }, { status: 201 }));
  await submission;
  assert.equal(app.nodes.get('register-success').hidden, false);
  assert.equal(app.getUser(), null);
  assert.equal(app.requests.length, 0);

  app.navigate('#login');
  assert.equal(app.nodes.get('username').value, 'demo.member176');
  assert.equal(app.nodes.get('password').value, '');
  app.nodes.get('password').value = ' abc12😀 ';
  const login = app.nodes.get('login-form').listeners.submit(event);
  const loginRequest = app.take('/auth/login', 'POST');
  assert.deepEqual(JSON.parse(loginRequest.body), JSON.parse(request.body));
  loginRequest.resolve(Response.json({ id: 2, role: 'MEMBER', csrf_token: 'member-token' }));
  await login;
  await flush();
  assert.equal(app.nodes.get('equipment').hidden, false);
});

const handedOver = {
  id: 42,
  status: 'HANDED_OVER',
  equipment_name: 'Máy chiếu demo',
  equipment_asset_code: 'DEMO-01',
  borrower_username: 'demo-member',
  start_at: '2026-11-17T09:00:00Z',
  end_at: '2026-11-17T10:00:00Z',
  created_at: '2026-11-17T08:00:00Z',
};
const returned = {
  ...handedOver,
  status: 'RETURNED',
  returned_by: 1,
  returned_by_username: 'demo-manager',
  returned_at: '2026-11-17T09:30:00Z',
};
const handedOverPath = '/loan-requests?status=HANDED_OVER';
const returnAction = (app) => app.nodes.get('management-rows').children[0].children[1].children.at(-1);

test('a fresh manager page can look up a returned request by code from the empty handed-over list', async () => {
  const app = setup();
  app.openManagement('#management/handed-over');
  app.take(handedOverPath).resolve(Response.json([]));
  await flush();
  const lookup = app.nodes.get('return-lookup');
  const input = app.nodes.get('return-lookup-id');
  const submit = () => lookup.listeners.submit({ preventDefault() {} });
  assert.equal(lookup.hidden, false);
  assert.equal(app.nodes.get('return-detail-link').hidden, true);
  input.value = 'YC-2147483648';
  submit();
  assert.match(app.nodes.get('return-lookup-error').textContent, /hợp lệ/);
  assert.equal(app.requests.length, 0);
  input.value = ' yc-42 ';
  submit();
  app.navigate();
  assert.equal(lookup.hidden, true);
  assert.match(app.nodes.get('management-status').textContent, /Đang tải chi tiết/);
  app.take('/loan-requests/42').resolve(Response.json(returned));
  await flush();
  const [info, actions] = app.nodes.get('management-rows').children[0].children;
  assert.match(info.children.at(-1).textContent, /demo-manager.*16:30/);
  assert.equal(actions.children.length, 0);
});

async function loadHandedOver(app, suffix = '') {
  app.openManagement('#management/handed-over' + suffix);
  app.take(suffix ? '/loan-requests' + suffix : handedOverPath)
    .resolve(Response.json(suffix ? handedOver : [handedOver]));
  await flush();
}

test('return confirmation sends one CSRF-protected POST and keeps the receipt if list reload fails', async () => {
  const app = setup();
  await loadHandedOver(app);
  returnAction(app).click();
  const dialog = app.nodes.get('decision-dialog');
  assert.equal(dialog.open, true);
  assert.match(app.nodes.get('decision-title').textContent, /YC-42/);
  assert.match(app.nodes.get('decision-summary').textContent, /Máy chiếu demo/);
  dialog.returnValue = 'cancel';
  dialog.listeners.close();
  assert.equal(app.requests.length, 0);
  returnAction(app).click();
  dialog.returnValue = 'confirm';
  dialog.listeners.close();
  assert.equal(returnAction(app).disabled, true);
  returnAction(app).click();
  const post = app.take('/loan-requests/42/return', 'POST');
  assert.equal(post.headers['X-CSRF-Token'], manager.csrf_token);
  assert.equal(app.requests.length, 0);
  post.resolve(Response.json(returned));
  await flush();
  app.take(handedOverPath).reject(new TypeError('demo network error'));
  await flush();
  assert.match(app.nodes.get('management-feedback').textContent, /Đã trả.*demo-manager.*16:30/);
  assert.equal(app.nodes.get('return-detail-link').href, '#management/handed-over/42');
  assert.equal(app.nodes.get('management-refresh').textContent, 'Thử tải lại');
  assert.equal(app.nodes.get('management-rows').children.length, 0);
  app.nodes.get('management-refresh').click();
  app.take(handedOverPath).resolve(Response.json([]));
  await flush();
  assert.equal(app.nodes.get('management-status').textContent, 'Chưa có yêu cầu đã giao.');
});

for (const failure of ['network', 'conflict']) {
  test(`return reconciles ${failure} with detail and displays the saved receipt`, async () => {
    const app = setup();
    await loadHandedOver(app, '/42');
    const submitting = app.submitDecision({ item: handedOver, verb: 'return', user: app.getUser() });
    const post = app.take('/loan-requests/42/return', 'POST');
    if (failure === 'network') post.reject(new TypeError('demo network error'));
    else post.resolve(Response.json({ code: 'INVALID_TRANSITION' }, { status: 409 }));
    await flush();
    app.take('/loan-requests/42').reject(new TypeError('demo read error'));
    await submitting;
    assert.equal(returnAction(app).disabled, true);
    const [retry] = app.nodes.get('management-recovery').children;
    assert.match(retry.textContent, /Thử tải lại chi tiết/);
    retry.click();
    app.take('/loan-requests/42').resolve(Response.json(returned));
    await flush();
    const [info, actions] = app.nodes.get('management-rows').children[0].children;
    assert.match(info.children.at(-1).textContent, /demo-manager.*16:30/);
    assert.equal(actions.children.length, 0);
    assert.equal(app.requests.length, 0);
  });
}

test('return can be confirmed again after reading an unchanged status with a refreshed CSRF token', async () => {
  const app = setup();
  await loadHandedOver(app, '/42');
  const submitting = app.submitDecision({ item: handedOver, verb: 'return', user: app.getUser() });
  app.take('/loan-requests/42/return', 'POST').resolve(Response.json({ code: 'CSRF_INVALID' }, { status: 403 }));
  await flush();
  app.take('/auth/me').resolve(Response.json({ ...manager, csrf_token: 'refreshed-token' }));
  await flush();
  app.take('/loan-requests/42').resolve(Response.json(handedOver));
  await submitting;
  assert.equal(returnAction(app).disabled, false);
  assert.equal(app.getUser().csrf_token, 'refreshed-token');
});

test('member cannot open a management return route', () => {
  const app = setup();
  app.openManagement('#management/handed-over', 'MEMBER');
  assert.equal(app.nodes.get('return-lookup').hidden, true);
  app.openManagement('#management/handed-over/42', 'MEMBER');
  assert.equal(app.nodes.get('handed-over-link').hidden, true);
  assert.equal(app.nodes.get('management-status').textContent, 'Bạn không có quyền truy cập.');
  assert.equal(app.requests.length, 0);
});

test('handover preserves the rendered detail when POST returns only loan fields', async () => {
  const item = {
    id: 42,
    status: 'APPROVED',
    equipment_name: 'Máy chiếu demo',
    equipment_asset_code: 'DEMO-01',
    borrower_username: 'demo-member',
    start_at: '2026-11-17T09:00:00Z',
    end_at: '2026-11-17T10:00:00Z',
    created_at: '2026-11-17T08:00:00Z',
  };
  const app = setup();
  app.showApprovedDetail(item);
  const submitting = app.submitDecision({ item, verb: 'handover', user: app.getUser() });
  const { equipment_name, equipment_asset_code, borrower_username, ...loan } = item;
  app.take('/loan-requests/42/handover', 'POST').resolve(Response.json({ ...loan, status: 'HANDED_OVER' }));
  await submitting;

  const [row] = app.nodes.get('management-rows').children;
  const [info, actions] = row.children;
  assert.equal(info.children[0].textContent, `${equipment_name} · ${equipment_asset_code}`);
  assert.equal(info.children[2].textContent, `YC-42 · Người gửi ${borrower_username}`);
  assert.equal(info.children.at(-1).textContent, 'Đã giao');
  assert.equal(actions.children.length, 0);
});

for (const [verb, status] of [['approve', 'APPROVED'], ['reject', 'REJECTED']]) {
  test(`${verb} releases the queue after the same session is verified`, async () => {
    const app = setup();
    const session = app.getUser();
    const submitting = app.submitDecision({ item: pending, verb, user: session });
    const post = app.take('/loan-requests/42/' + verb, 'POST');
    const checking = app.checkSession();
    post.resolve(Response.json({ status }));
    await flush();
    assert.equal(app.managementBusy(), true);
    app.take('/auth/me').resolve(Response.json(manager));
    await Promise.all([checking, submitting]);
    assert.equal(app.getUser(), session);
    assert.equal(app.managementBusy(), false);
    assert.equal(app.managementDecisions.has(42), false);
  });
}

test('a conflict reconciles after retrying a failed session check', async () => {
  const app = setup();
  const session = app.getUser();
  const submitting = app.submitDecision({ item: pending, verb: 'approve', user: session });
  const post = app.take('/loan-requests/42/approve', 'POST');
  const checking = app.checkSession();
  app.take('/auth/me').reject(new TypeError('demo network error'));
  await checking;
  post.resolve(Response.json({ code: 'SCHEDULE_CONFLICT' }, { status: 409 }));
  await flush();
  assert.equal(app.requests.length, 0);
  const retrying = app.checkSession();
  app.take('/auth/me').resolve(Response.json(manager));
  await retrying;
  await flush();
  app.take('/loan-requests/42').resolve(Response.json(pending));
  await flush();
  app.take('/loan-requests').resolve(Response.json([pending]));
  await submitting;
  assert.equal(app.getUser(), session);
  assert.equal(app.managementBusy(), false);
  assert.equal(app.managementDecisions.get(42).locked, false);
});

test('an old decision cannot reconcile in a replacement session', async () => {
  const app = setup();
  const session = app.getUser();
  const submitting = app.submitDecision({ item: pending, verb: 'reject', user: session });
  const post = app.take('/loan-requests/42/reject', 'POST');
  const checking = app.checkSession();
  post.reject(new TypeError('demo network error'));
  await flush();
  app.take('/auth/me').resolve(Response.json({ ...manager, csrf_token: 'replacement-token' }));
  await Promise.all([checking, submitting]);
  assert.notEqual(app.getUser(), session);
  assert.equal(app.requests.length, 0);
  assert.equal(app.managementBusy(), false);
  assert.equal(app.managementDecisions.size, 0);
});

test('logout CSRF recovery clears decisions from the replaced session', async () => {
  const app = setup();
  const session = app.getUser();
  const submitting = app.submitDecision({ item: pending, verb: 'approve', user: session });
  const post = app.take('/loan-requests/42/approve', 'POST');
  assert.equal(app.managementBusy(), true);

  const loggingOut = app.logout();
  app.take('/auth/logout', 'POST').resolve(Response.json({ code: 'CSRF_INVALID' }, { status: 403 }));
  await flush();
  const replacement = { ...manager, csrf_token: 'replacement-token' };
  app.take('/auth/me').resolve(Response.json(replacement));
  await loggingOut;

  post.resolve(Response.json({ status: 'APPROVED' }));
  await submitting;
  assert.notEqual(app.getUser(), session);
  assert.equal(app.getUser().csrf_token, replacement.csrf_token);
  assert.equal(app.managementBusy(), false);
  assert.equal(app.managementDecisions.size, 0);
  assert.equal(app.requests.length, 0);
});
