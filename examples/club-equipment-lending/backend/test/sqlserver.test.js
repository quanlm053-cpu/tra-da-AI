import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { test } from 'node:test';
import { createApp } from '../app.js';
import { connectDatabase, migrate, sqlServerStore, seedDemo } from '../database.js';
import { cookie, expectError, login, origin, register, serve } from './helpers.js';

test('SQL Server migration, repeatable demo seed and session lifecycle through HTTP', async (t) => {
  const connectionString = process.env.TEST_DATABASE_URL;
  assert.ok(connectionString, 'Set TEST_DATABASE_URL to a disposable SQL Server database');
  const schema = 'lending_test_' + randomBytes(8).toString('hex');
  const { pool, sql } = await connectDatabase({ ...process.env, DATABASE_URL: connectionString });
  const query = statement => pool.request().query(statement);
  const users = `[${schema}].[users]`;
  const sessions = `[${schema}].[sessions]`;
  const equipment = `[${schema}].[equipment]`;
  const loans = `[${schema}].[loan_requests]`;
  const events = `[${schema}].[loan_events]`;
  t.after(async () => {
    try {
      if (created) await query(`DROP TABLE IF EXISTS ${events}; DROP TABLE IF EXISTS ${loans}; DROP TABLE IF EXISTS ${sessions}; DROP TABLE IF EXISTS ${equipment}; DROP TABLE IF EXISTS ${users}; DROP SCHEMA [${schema}];`);
    } finally {
      await pool.close();
    }
  });
  let created = false;
  const db = (await query('SELECT DB_NAME() AS name')).recordset[0].name;
  assert.equal(db, 'ClubEquipmentLending_Test', 'Use the isolated Lending test database');
  await query(`CREATE SCHEMA [${schema}]`);
  created = true;
  await migrate(pool, sql, schema);
  await migrate(pool, sql, schema);

  const env = {
    LENDING_ENV: 'test',
    DEMO_MEMBER_PASSWORD: 'synthetic-member-test',
    DEMO_MANAGER_PASSWORD: 'synthetic-manager-test',
  };
  await assert.rejects(seedDemo(pool, sql, { ...env, LENDING_ENV: 'production' }, schema));
  await seedDemo(pool, sql, env, schema);
  const initial = await query(`SELECT id, username, password_hash, role FROM ${users} ORDER BY username`);
  await seedDemo(pool, sql, env, schema);
  assert.deepEqual((await query(`SELECT id, username, password_hash, role FROM ${users} ORDER BY username`)).recordset, initial.recordset);
  assert.equal(initial.recordset.length, 2);
  assert.ok(initial.recordset.every((row) => row.password_hash.startsWith('$argon2id$')));

  const request = await serve(t, await createApp({
    store: sqlServerStore(pool, sql, schema), origin, logger: { error() {} },
  }));
  const member = await login(request, 'demo.member', env.DEMO_MEMBER_PASSWORD);
  const manager = await login(request, 'demo.manager', env.DEMO_MANAGER_PASSWORD);
  for (const [response, role] of [[member, 'MEMBER'], [manager, 'MANAGER']]) {
    assert.equal(response.status, 200);
    const headers = { Cookie: cookie(response) };
    const me = await request('/auth/me', { headers });
    assert.equal(me.status, 200);
    assert.equal((await me.json()).role, role);
    const list = await request('/equipment', { headers });
    assert.equal(list.status, 200);
    const items = await list.json();
    assert.deepEqual(items.map((item) => item.asset_code), ['DEMO-01', 'DEMO-02']);
    assert.notEqual(items[0].id, items[1].id);
    assert.equal(items[0].name, items[1].name);
  }

  const memberUser = await member.json();
  await query(`
    INSERT INTO ${loans} (equipment_id, borrower_id, start_at, end_at, status)
    SELECT e.id, u.id, fixture.start_at, fixture.end_at, fixture.status
    FROM ${equipment} e CROSS JOIN ${users} u CROSS JOIN (VALUES
      ('2026-11-16T01:30:00', '2026-11-16T03:00:00', 'APPROVED'),
      ('2026-11-16T03:00:00', '2026-11-16T04:00:00', 'HANDED_OVER'),
      ('2026-11-16T00:00:00', '2026-11-16T02:00:00', 'APPROVED'),
      ('2026-11-16T06:00:00', '2026-11-16T07:00:00', 'APPROVED'),
      ('2026-11-16T04:00:00', '2026-11-16T04:30:00', 'PENDING'),
      ('2026-11-16T04:30:00', '2026-11-16T05:00:00', 'REJECTED'),
      ('2026-11-16T05:00:00', '2026-11-16T06:00:00', 'RETURNED')
    ) fixture(start_at, end_at, status)
    WHERE e.asset_code = 'DEMO-01' AND u.username = 'demo.member';
  `);
  const [first, second] = await sqlServerStore(pool, sql, schema).listEquipment();
  const at = (time) => `2026-11-16T${time}:00.000Z`;
  async function expectSlots(id, from, to, expected, response = member) {
    const query = new URLSearchParams({ from, to });
    const result = await request(`/equipment/${id}/availability?${query}`, {
      headers: { Cookie: cookie(response) },
    });
    assert.equal(result.status, 200);
    assert.equal(result.headers.get('cache-control'), 'no-store');
    const body = await result.json();
    assert.equal(new Date(body.as_of).toISOString(), body.as_of);
    assert.deepEqual(body, {
      equipment_id: id,
      timezone: 'Asia/Bangkok',
      as_of: body.as_of,
      available: expected.map(([start_at, end_at]) => ({ start_at, end_at })),
    });
  }
  await expectSlots(first.id, '2026-11-16T09:00:00+07:00', '2026-11-16T13:00:00+07:00',
    [[at('04:00'), at('06:00')]]);
  await expectSlots(first.id, at('02:00'), at('06:00'), [[at('04:00'), at('06:00')]], manager);
  await expectSlots(first.id, at('02:00'), at('04:00'), []);
  await expectSlots(first.id, '2026-11-15T23:00:00.123Z', at('08:00'),
    [['2026-11-15T23:00:00.123Z', at('00:00')], [at('04:00'), at('06:00')], [at('07:00'), at('08:00')]]);
  await expectSlots(second.id, at('02:00'), at('06:00'), [[at('02:00'), at('06:00')]]);
  await query(`INSERT INTO ${users} (username, role, password_hash)
               SELECT 'demo.member.two', role, password_hash FROM ${users} WHERE username = 'demo.member'`);
  const other = await login(request, 'demo.member.two', env.DEMO_MEMBER_PASSWORD);
  assert.equal(other.status, 200);
  const otherUser = await other.json();
  const path = '/loan-requests';
  const auth = response => ({ headers: { Cookie: cookie(response) } });
  const post = (response, csrf, start, end) => request(path, {
    method: 'POST',
    headers: { Cookie: cookie(response), 'X-CSRF-Token': csrf, 'Content-Type': 'application/json' },
    body: JSON.stringify({ equipment_id: second.id, start_at: start, end_at: end }),
  });
  assert.deepEqual(await (await request(path, auth(other))).json(), []);
  const [firstPost, secondPost] = await Promise.all([
    post(member, memberUser.csrf_token, '2026-11-16T09:00:00+07:00', '2026-11-16T10:00:00+07:00'),
    post(other, otherUser.csrf_token, '2026-11-16T09:30:00+07:00', '2026-11-16T10:30:00+07:00'),
  ]);
  const [firstLoan, secondLoan] = await Promise.all([firstPost.json(), secondPost.json()]);
  for (const [response, loan] of [[firstPost, firstLoan], [secondPost, secondLoan]]) {
    assert.equal(response.status, 201);
    assert.equal(response.headers.get('location'), path + '/' + loan.id);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    assert.deepEqual(Object.keys(loan).sort(), ['created_at', 'end_at', 'equipment_id', 'id', 'start_at', 'status']);
    assert.equal(loan.status, 'PENDING');
    assert.equal(loan.equipment_id, second.id);
  }
  assert.notEqual(firstLoan.id, secondLoan.id);
  assert.equal(firstLoan.start_at, at('02:00'));
  assert.equal(firstLoan.end_at, at('03:00'));
  assert.deepEqual(await (await request(path, auth(other))).json(), [secondLoan]);
  assert.deepEqual((await (await request(path, auth(member))).json())
    .filter(loan => loan.equipment_id === second.id), [firstLoan]);
  await expectSlots(second.id, at('02:00'), at('06:00'), [[at('02:00'), at('06:00')]]);
  await expectError(await request(path + '/' + firstLoan.id, auth(other)), 404, 'NOT_FOUND');
  await expectError(await request(path + '/2147483647', auth(other)), 404, 'NOT_FOUND');
  await t.test('concurrent registrations commit one member and enforce member permissions', async subtest => {
    const { pool: otherPool } = await connectDatabase({ ...process.env, DATABASE_URL: connectionString });
    subtest.after(() => otherPool.close());
    const requestTwo = await serve(subtest, await createApp({
      store: sqlServerStore(otherPool, sql, schema), origin,
    }));
    const password = ' abc123😀';
    for (const extra of [{ role: 'MANAGER' }, { extra: true }]) {
      await expectError(await register(request, { username: 'blocked.member', password, ...extra }),
        400, 'INVALID_INPUT');
    }
    await expectError(await register(request, { username: 'registered.normalized', password: password.trim() }),
      400, 'INVALID_INPUT');
    assert.equal((await query(`SELECT COUNT(*) AS total FROM ${users}
      WHERE username = 'registered.normalized'`)).recordset[0].total, 0);
    for (const [username, alternative] of [
      ['registered.exact', 'registered.exact'], ['registered.normalized', '  REGISTERED.Normalized  '],
    ]) {
      const responses = await Promise.all([
        register(request, { username, password }),
        register(requestTwo, { username: alternative, password }),
      ]);
      assert.deepEqual(responses.map(response => response.status).sort(), [201, 409]);
      const created = responses.find(response => response.status === 201);
      assert.equal(created.headers.get('set-cookie'), null);
      assert.deepEqual(await created.json(), { username, role: 'MEMBER' });
      await expectError(responses.find(response => response.status === 409), 409, 'USERNAME_TAKEN');
    }
    const { recordset: registered } = await query(`
      SELECT username, role, password_hash FROM ${users}
      WHERE username IN ('blocked.member', 'registered.exact', 'registered.normalized') ORDER BY username
    `);
    assert.deepEqual(registered.map(({ username, role }) => [username, role]), [
      ['registered.exact', 'MEMBER'], ['registered.normalized', 'MEMBER'],
    ]);
    for (const row of registered) {
      assert.match(row.password_hash, /^\$argon2id\$/);
      assert.notEqual(row.password_hash, password);
    }
    await expectError(await login(requestTwo, 'registered.normalized', password.trim()), 401, 'INVALID_CREDENTIALS');
    const signedIn = await login(requestTwo, 'registered.normalized', password);
    assert.equal(signedIn.status, 200);
    const session = await signedIn.json();
    assert.equal(session.role, 'MEMBER');
    assert.equal((await requestTwo('/equipment', auth(signedIn))).status, 200);
    await expectError(await requestTwo(`${path}/${firstLoan.id}/approve`, {
      method: 'POST',
      headers: { ...auth(signedIn).headers, Origin: origin, 'X-CSRF-Token': session.csrf_token },
    }), 403, 'FORBIDDEN');
    assert.equal((await query(`SELECT status FROM ${loans} WHERE id = ${firstLoan.id}`)).recordset[0].status,
      'PENDING');
    assert.equal((await query(`SELECT COUNT(*) AS total FROM ${events} WHERE request_id = ${firstLoan.id}`))
      .recordset[0].total, 0);
    const logout = await requestTwo('/auth/logout', {
      method: 'POST',
      headers: { ...auth(signedIn).headers, 'X-CSRF-Token': session.csrf_token },
    });
    assert.equal(logout.status, 204);
  });
  await t.test('manager decisions serialize overlaps and record committed transitions', async subtest => {
    const { pool: otherPool } = await connectDatabase({ ...process.env, DATABASE_URL: connectionString });
    subtest.after(() => otherPool.close());
    const requestTwo = await serve(subtest, await createApp({
      store: sqlServerStore(otherPool, sql, schema), origin,
    }));
    await query(`INSERT INTO ${users} (username, role, password_hash)
                 SELECT 'demo.manager.two', role, password_hash FROM ${users} WHERE username = 'demo.manager'`);
    const managerTwo = await login(requestTwo, 'demo.manager.two', env.DEMO_MANAGER_PASSWORD);
    assert.equal(managerTwo.status, 200);
    const managerUser = await manager.json();
    const managerTwoUser = await managerTwo.json();
    const decide = (loan, action, secondSession = false) => {
      const [send, response, user] = secondSession
        ? [requestTwo, managerTwo, managerTwoUser]
        : [request, manager, managerUser];
      return send(`${path}/${loan.id}/${action}`, {
        method: 'POST', headers: { Cookie: cookie(response), 'X-CSRF-Token': user.csrf_token },
      });
    };
    const detail = async (loan, response = manager) =>
      (await request(path + '/' + loan.id, auth(response))).json();
    const queue = async () => (await request(path, auth(manager))).json();
    const create = async (item, start, end) => {
      const response = await request(path, {
        method: 'POST',
        headers: { ...auth(member).headers, 'X-CSRF-Token': memberUser.csrf_token, 'Content-Type': 'application/json' },
        body: JSON.stringify({ equipment_id: item.id, start_at: at(start), end_at: at(end) }),
      });
      assert.equal(response.status, 201);
      return response.json();
    };
    const history = async (...requests) => (await query(`
      SELECT request_id, actor_id, from_status, to_status, occurred_at FROM ${events}
      WHERE request_id IN (${requests.map(loan => loan.id).join(', ')}) ORDER BY id
    `)).recordset;

    const both = [firstLoan, secondLoan];
    await query(`UPDATE ${loans} SET created_at = '2026-11-16T00:00:00'
                 WHERE id IN (${firstLoan.id}, ${secondLoan.id})`);
    const pending = await queue();
    assert.ok(pending.every(row => row.status === 'PENDING'));
    const managed = pending.filter(row => row.equipment_id === second.id);
    assert.deepEqual(managed.map(row => row.id), both.map(row => row.id).sort((a, b) => a - b));
    assert.deepEqual(await detail(firstLoan), {
      ...firstLoan, created_at: at('00:00'), borrower_id: memberUser.id,
      borrower_username: memberUser.username, equipment_asset_code: second.asset_code, equipment_name: second.name,
    });
    const approvals = await Promise.all([
      decide(firstLoan, 'approve'), decide(secondLoan, 'approve', true),
    ]);
    assert.deepEqual(approvals.map(row => row.status).sort(), [200, 409]);
    const winnerIndex = approvals.findIndex(row => row.status === 200);
    const winner = both[winnerIndex];
    const loser = both[1 - winnerIndex];
    const approved = await approvals[winnerIndex].json();
    assert.equal(approved.id, winner.id);
    assert.equal(approved.status, 'APPROVED');
    await expectError(approvals[1 - winnerIndex], 409, 'SCHEDULE_CONFLICT');
    assert.equal((await detail(winner, winnerIndex === 0 ? member : other)).status, 'APPROVED');
    assert.deepEqual((await queue()).filter(row => row.equipment_id === second.id).map(row => row.id), [loser.id]);
    const overlapEvents = await history(winner, loser);
    assert.equal(overlapEvents.length, 1);
    const [event] = overlapEvents;
    assert.deepEqual([event.request_id, event.actor_id, event.from_status, event.to_status],
      [winner.id, [managerUser, managerTwoUser][winnerIndex].id, 'PENDING', 'APPROVED']);
    assert.ok(event.occurred_at instanceof Date);
    await expectSlots(second.id, winner.start_at, winner.end_at, []);
    const rejected = await decide(loser, 'reject');
    assert.equal(rejected.status, 200);
    assert.equal((await rejected.json()).status, 'REJECTED');
    assert.deepEqual((await history(loser)).map(row => row.to_status), ['REJECTED']);

    const edgeLeft = await create(second, '08:00', '09:00');
    const edgeRight = await create(second, '09:00', '10:00');
    const different = await create(first, '10:00', '11:00');
    for (const [left, right] of [[edgeLeft, edgeRight], [different, await create(second, '10:00', '11:00')]]) {
      const results = await Promise.all([decide(left, 'approve'), decide(right, 'approve', true)]);
      assert.deepEqual(results.map(row => row.status), [200, 200]);
      assert.equal((await history(left, right)).length, 2);
    }
    const raced = await create(second, '12:00', '13:00');
    const race = await Promise.all([decide(raced, 'approve'), decide(raced, 'reject', true)]);
    assert.deepEqual(race.map(row => row.status).sort(), [200, 409]);
    await expectError(race.find(row => row.status === 409), 409, 'INVALID_TRANSITION');
    await expectError(await decide(raced, 'approve'), 409, 'INVALID_TRANSITION');
    assert.equal((await history(raced)).length, 1);

    for (const [status, hour] of [['HANDED_OVER', 14], ['PENDING', 15], ['REJECTED', 16], ['RETURNED', 17]]) {
      const fixture = await create(second, `${hour}:00`, `${hour}:30`);
      await query(`UPDATE ${loans} SET status = '${status}' WHERE id = ${fixture.id}`);
      const candidate = await create(second, `${hour}:00`, `${hour}:30`);
      const result = await decide(candidate, 'approve');
      if (status === 'HANDED_OVER') await expectError(result, 409, 'SCHEDULE_CONFLICT');
      else assert.equal(result.status, 200);
    }

    const rollback = await create(second, '18:00', '19:00');
    await query(`ALTER TABLE ${events} ADD CONSTRAINT test_event_failure CHECK (request_id <> ${rollback.id})`);
    try {
      await expectError(await decide(rollback, 'approve'), 500, 'INTERNAL_ERROR');
      assert.equal((await detail(rollback)).status, 'PENDING');
      assert.deepEqual(await history(rollback), []);
      await expectSlots(second.id, rollback.start_at, rollback.end_at, [[rollback.start_at, rollback.end_at]]);
    } finally {
      await query(`ALTER TABLE ${events} DROP CONSTRAINT test_event_failure`);
    }
    assert.equal((await decide(rollback, 'approve')).status, 200);
    assert.equal((await history(rollback)).length, 1);

    const approvedQueue = async () => (await request(path + '?status=APPROVED', auth(manager))).json();
    assert.ok((await approvedQueue()).some(row => row.id === edgeLeft.id && row.status === 'APPROVED'));
    await expectError(await decide(edgeLeft, 'handover'), 409, 'EQUIPMENT_IN_USE');
    assert.equal((await detail(edgeLeft)).status, 'APPROVED');
    assert.deepEqual((await history(edgeLeft)).map(row => row.to_status), ['APPROVED']);
    const handedOverQueue = async () => (await request(path + '?status=HANDED_OVER', auth(manager))).json();
    for (const fixture of await handedOverQueue()) {
      assert.equal((await decide(fixture, 'return')).status, 200);
    }

    await query(`ALTER TABLE ${events} ADD CONSTRAINT test_handover_failure
                 CHECK (request_id <> ${edgeLeft.id} OR to_status <> 'HANDED_OVER')`);
    try {
      await expectError(await decide(edgeLeft, 'handover'), 500, 'INTERNAL_ERROR');
      assert.equal((await detail(edgeLeft)).status, 'APPROVED');
      assert.deepEqual((await history(edgeLeft)).map(row => row.to_status), ['APPROVED']);
    } finally {
      await query(`ALTER TABLE ${events} DROP CONSTRAINT test_handover_failure`);
    }

    const utcNow = async () => (await query('SELECT CAST(SYSUTCDATETIME() AS datetime2(3)) AS now')).recordset[0].now;
    const before = await utcNow();
    const adjacent = [edgeLeft, edgeRight];
    const handovers = await Promise.all([
      decide(edgeLeft, 'handover'), decide(edgeRight, 'handover', true),
    ]);
    assert.deepEqual(handovers.map(row => row.status).sort(), [200, 409]);
    const deliveredIndex = handovers.findIndex(row => row.status === 200);
    const delivered = adjacent[deliveredIndex];
    const waiting = adjacent[1 - deliveredIndex];
    const after = await utcNow();
    assert.deepEqual(await handovers[deliveredIndex].json(),
      { ...delivered, status: 'HANDED_OVER', borrower_id: memberUser.id });
    await expectError(handovers[1 - deliveredIndex], 409, 'EQUIPMENT_IN_USE');
    assert.equal((await detail(waiting)).status, 'APPROVED');
    assert.equal((await detail(delivered, member)).status, 'HANDED_OVER');
    await expectError(await request(path + '/' + delivered.id, auth(other)), 404, 'NOT_FOUND');
    assert.ok((await (await request(path, auth(member))).json())
      .some(row => row.id === delivered.id && row.status === 'HANDED_OVER'));
    const approvedIds = (await approvedQueue()).map(row => row.id);
    assert.ok(approvedIds.includes(waiting.id));
    assert.ok(!approvedIds.includes(delivered.id));
    const deliveryEvents = (await history(...adjacent)).filter(row => row.to_status === 'HANDED_OVER');
    assert.equal(deliveryEvents.length, 1);
    const [delivery] = deliveryEvents;
    assert.deepEqual([delivery.request_id, delivery.actor_id, delivery.from_status],
      [delivered.id, [managerUser, managerTwoUser][deliveredIndex].id, 'APPROVED']);
    assert.ok(delivery.occurred_at >= before && delivery.occurred_at <= after);
    await assert.rejects(query(`UPDATE ${loans} SET status = 'HANDED_OVER' WHERE id = ${waiting.id}`),
      error => Number(error.number) === 2601);

    const duplicates = await Promise.all([
      decide(different, 'handover'), decide(different, 'handover', true),
    ]);
    assert.deepEqual(duplicates.map(row => row.status).sort(), [200, 409]);
    await expectError(duplicates.find(row => row.status === 409), 409, 'INVALID_TRANSITION');
    assert.equal((await history(different)).filter(row => row.to_status === 'HANDED_OVER').length, 1);
    assert.ok((await handedOverQueue()).some(row => row.id === delivered.id));
    await expectSlots(second.id, edgeLeft.start_at, edgeRight.end_at, []);
    await query(`ALTER TABLE ${events} ADD CONSTRAINT test_return_failure
                 CHECK (request_id <> ${delivered.id} OR to_status <> 'RETURNED')`);
    try {
      await expectError(await decide(delivered, 'return'), 500, 'INTERNAL_ERROR');
      assert.equal((await detail(delivered)).status, 'HANDED_OVER');
      assert.deepEqual((await history(delivered)).map(row => row.to_status), ['APPROVED', 'HANDED_OVER']);
      await expectSlots(second.id, edgeLeft.start_at, edgeRight.end_at, []);
      await expectError(await decide(waiting, 'handover', true), 409, 'EQUIPMENT_IN_USE');
    } finally {
      await query(`ALTER TABLE ${events} DROP CONSTRAINT test_return_failure`);
    }

    const beforeReturn = await utcNow();
    const returns = await Promise.all([decide(delivered, 'return'), decide(delivered, 'return', true)]);
    const afterReturn = await utcNow();
    assert.deepEqual(returns.map(response => response.status).sort(), [200, 409]);
    const returnedIndex = returns.findIndex(response => response.status === 200);
    await expectError(returns[1 - returnedIndex], 409, 'INVALID_TRANSITION');
    const receiver = [managerUser, managerTwoUser][returnedIndex];
    const returnEvents = (await history(delivered)).filter(row => row.to_status === 'RETURNED');
    assert.equal(returnEvents.length, 1);
    const [returned] = returnEvents;
    assert.deepEqual([returned.actor_id, returned.from_status], [receiver.id, 'HANDED_OVER']);
    assert.ok(returned.occurred_at >= beforeReturn && returned.occurred_at <= afterReturn);
    const returnAudit = {
      returned_at: returned.occurred_at.toISOString(),
      returned_by: receiver.id,
      returned_by_username: receiver.username,
    };
    const memberReturn = { ...delivered, status: 'RETURNED' };
    assert.deepEqual(await returns[returnedIndex].json(), { ...memberReturn, borrower_id: memberUser.id, ...returnAudit });
    assert.deepEqual(await detail(delivered), {
      ...memberReturn, borrower_id: memberUser.id, borrower_username: memberUser.username,
      equipment_asset_code: second.asset_code, equipment_name: second.name, ...returnAudit,
    });
    assert.deepEqual(await detail(delivered, member), memberReturn);
    assert.ok((await (await request(path, auth(member))).json())
      .some(row => row.id === delivered.id && row.status === 'RETURNED'));
    await expectError(await request(path + '/' + delivered.id, auth(other)), 404, 'NOT_FOUND');
    assert.ok(!(await handedOverQueue()).some(row => row.id === delivered.id));
    await expectSlots(second.id, edgeLeft.start_at, edgeRight.end_at, [[delivered.start_at, delivered.end_at]]);
    assert.equal((await decide(waiting, 'handover')).status, 200);

    const next = await create(second, '19:00', '20:00');
    assert.equal((await decide(next, 'approve')).status, 200);
    const [returnWaiting, handoverNext] = await Promise.all([
      decide(waiting, 'return'), decide(next, 'handover', true),
    ]);
    assert.equal(returnWaiting.status, 200);
    assert.equal((await detail(waiting)).status, 'RETURNED');
    if (handoverNext.status === 409) {
      await expectError(handoverNext, 409, 'EQUIPMENT_IN_USE');
      assert.equal((await detail(next)).status, 'APPROVED');
      assert.equal((await decide(next, 'handover', true)).status, 200);
    } else {
      assert.equal(handoverNext.status, 200);
    }
    assert.equal((await detail(next)).status, 'HANDED_OVER');
    for (const fixture of await handedOverQueue()) {
      assert.equal((await decide(fixture, 'return')).status, 200);
    }

    await requestTwo('/auth/logout', {
      method: 'POST', headers: { Cookie: cookie(managerTwo), 'X-CSRF-Token': managerTwoUser.csrf_token },
    });
  });
  await query(`UPDATE ${loans} SET created_at = '2026-11-16T02:00:00' WHERE borrower_id = ${memberUser.id}`);
  const memberLoans = await (await request(path, auth(member))).json();
  assert.deepEqual(memberLoans.map(loan => loan.id), memberLoans.map(loan => loan.id).sort((a, b) => b - a));
  await request('/auth/logout', {
    method: 'POST', headers: { Cookie: cookie(other), 'X-CSRF-Token': otherUser.csrf_token },
  });
  await expectSlots(first.id, at('02:00'), at('06:00'), [[at('03:00'), at('06:00')]]);

  const logout = await request('/auth/logout', {
    method: 'POST',
    headers: { Cookie: cookie(member), 'X-CSRF-Token': memberUser.csrf_token },
  });
  assert.equal(logout.status, 204);
  assert.equal((await query(`SELECT 1 AS present FROM ${sessions}`)).recordset.length, 1);
  await expectError(await request('/equipment', { headers: { Cookie: cookie(member) } }), 401, 'AUTH_REQUIRED');
  await query(`UPDATE ${sessions} SET expires_at = DATEADD(second, -1, SYSUTCDATETIME())`);
  await expectError(await request('/equipment', { headers: { Cookie: cookie(manager) } }), 401, 'AUTH_REQUIRED');
  await expectError(await request(`/equipment/${first.id}/availability?from=${at('02:00')}&to=${at('06:00')}`, {
    headers: { Cookie: cookie(manager) },
  }), 401, 'AUTH_REQUIRED');
  await sqlServerStore(pool, sql, schema).deleteExpiredSessions();
  assert.equal((await query(`SELECT 1 AS present FROM ${sessions}`)).recordset.length, 0);
});
