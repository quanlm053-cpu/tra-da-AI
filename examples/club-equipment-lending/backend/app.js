import { isUtf8 } from 'node:buffer';
import { createHash, createHmac, randomBytes, timingSafeEqual } from 'node:crypto';
import { isIP } from 'node:net';
import { availabilityInput, availableSlots, utcTime } from './availability.js';
import { sessionSeconds } from './database.js';
import { hashPassword, verifyPassword } from './password.js';

const cookieName = '__Host-lending_session';
const cookieAttributes = 'Path=/; HttpOnly; Secure; SameSite=Lax';
const safeMethods = new Set(['GET', 'HEAD', 'OPTIONS']);
const sessionHash = (token) => createHash('sha256').update(token).digest();
const csrfToken = (token) => createHmac('sha256', token).update('lending csrf v1').digest('base64url');

function json(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(body));
}

function error(res, status, code) {
  json(res, status, { code });
}

function sessionToken(req) {
  const cookies = (req.headers.cookie ?? '').split(';').map((cookie) => cookie.trim());
  const matches = cookies.filter((cookie) => cookie.startsWith(cookieName + '='));
  if (matches.length !== 1) return;
  const token = matches[0].slice(cookieName.length + 1);
  if (/^[A-Za-z0-9_-]{43}$/.test(token)) return token;
}

function hasValidCsrf(req, expected) {
  const value = req.headers['x-csrf-token'];
  return typeof value === 'string' && /^[A-Za-z0-9_-]{43}$/.test(value) &&
    timingSafeEqual(Buffer.from(value), Buffer.from(expected));
}

async function readJson(req) {
  if (req.headers['content-type']?.split(';')[0].trim().toLowerCase() !== 'application/json') return;
  const chunks = [];
  let size = 0;
  for await (const chunk of req.iterator({ destroyOnReturn: false })) {
    size += chunk.length;
    if (size > 8192) return;
    chunks.push(chunk);
  }
  const body = Buffer.concat(chunks);
  if (!isUtf8(body)) return;
  try {
    return JSON.parse(body.toString('utf8'));
  } catch {
    return;
  }
}

async function credentials(req) {
  const input = await readJson(req);
  if (typeof input?.username !== 'string' || !input.username.trim() || input.username.length > 128 ||
      typeof input.password !== 'string' || !input.password || Buffer.byteLength(input.password) > 1024) return;
  return { username: input.username.trim().toLowerCase(), password: input.password };
}

async function registrationInput(req) {
  const input = await readJson(req);
  if (!input || Object.keys(input).length !== 2 ||
      !Object.hasOwn(input, 'username') || !Object.hasOwn(input, 'password') ||
      typeof input.username !== 'string' || input.username.length > 128 ||
      typeof input.password !== 'string' || !input.password.isWellFormed() ||
      Buffer.byteLength(input.password) > 1024 ||
      !input.password.trim() || [...input.password].length < 8) return;
  const username = input.username.trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9._-]{2,63}$/.test(username)) return;
  return { username, password: input.password };
}

const validId = (id) => Number.isInteger(id) && id > 0 && id <= 2147483647;
const loanRequestId = (id) => /^\d+$/.test(id) && validId(Number(id)) ? Number(id) : undefined;
const loanRoles = new Set(['MEMBER', 'MANAGER']);

function loanInput(input) {
  if (!input || typeof input !== 'object' || Object.keys(input).length !== 3 ||
      !validId(input.equipment_id)) return;
  const start = utcTime(input.start_at);
  const end = utcTime(input.end_at);
  if (start && end && start < end) return { equipmentId: input.equipment_id, start, end };
}

function authLimiter(now) {
  const windowMs = 60_000;
  let endsAt = 0;
  const counts = new Map();
  return (address) => {
    const time = now();
    if (time >= endsAt) {
      endsAt = time + windowMs;
      counts.clear();
    }
    const count = counts.get(address) ?? 0;
    if (count >= 10 || (count === 0 && counts.size >= 10_000)) return Math.ceil((endsAt - time) / 1000);
    counts.set(address, count + 1);
    return 0;
  };
}

function clientAddress(req, trustedProxyIp) {
  const peer = req.socket.remoteAddress;
  const forwarded = req.headers['x-lending-client-ip'];
  return peer === trustedProxyIp && typeof forwarded === 'string' && isIP(forwarded)
    ? forwarded
    : peer;
}

function identity(user, csrf) {
  return { id: user.id, username: user.username, role: user.role, csrf_token: csrf };
}

export async function createApp({ store, origin, trustedProxyIp, routes = new Map(), now = Date.now, logger = console }) {
  const dummyHash = await hashPassword(randomBytes(32).toString('base64url'));
  const loginRetryAfter = authLimiter(now);
  const registerRetryAfter = authLimiter(now);
  const protectedRoutes = new Map(routes);
  protectedRoutes.set('GET /auth/me', {
    handle: (_req, res, session) => json(res, 200, session.user),
  });
  protectedRoutes.set('POST /auth/logout', {
    async handle(_req, res, session) {
      await store.deleteSession(session.hash);
      res.setHeader('Set-Cookie', cookieName + '=; Max-Age=0; ' + cookieAttributes);
      res.writeHead(204).end();
    },
  });
  protectedRoutes.set('GET /equipment', {
    handle: async (_req, res) => json(res, 200, await store.listEquipment()),
  });
  protectedRoutes.set('POST /loan-requests', {
    role: 'MEMBER',
    async handle(req, res, session) {
      const input = loanInput(await readJson(req));
      if (!input) return error(res, 400, 'INVALID_INPUT');
      const loan = await store.createLoanRequest(session.user.id, input);
      if (!loan) return error(res, 404, 'NOT_FOUND');
      res.setHeader('Location', '/loan-requests/' + loan.id);
      json(res, 201, loan);
    },
  });
  protectedRoutes.set('GET /loan-requests', {
    roles: loanRoles,
    async handle(_req, res, { user }, { query }) {
      const status = query.get('status');
      const loans = user.role === 'MANAGER'
        ? await store.listManagedLoanRequests(['APPROVED', 'HANDED_OVER'].includes(status) ? status : 'PENDING')
        : await store.listLoanRequests(user.id);
      json(res, 200, loans);
    },
  });
  const loanDetailRoute = {
    roles: loanRoles,
    async handle(_req, res, { user }, { id }) {
      const requestId = loanRequestId(id);
      if (!requestId) return error(res, 400, 'INVALID_INPUT');
      const loan = user.role === 'MANAGER'
        ? await store.readManagedLoanRequest(requestId)
        : await store.readLoanRequest(user.id, requestId);
      if (!loan) return error(res, 404, 'NOT_FOUND');
      json(res, 200, loan);
    },
  };
  const loanDecisionRoute = {
    role: 'MANAGER',
    async handle(_req, res, { user }, { id, action }) {
      const requestId = loanRequestId(id);
      if (!requestId) return error(res, 400, action === 'handover' ? 'INVALID_REQUEST' : 'INVALID_INPUT');
      const target = { approve: 'APPROVED', reject: 'REJECTED', handover: 'HANDED_OVER', return: 'RETURNED' }[action];
      const { loan, code } = await store.decideLoanRequest(requestId, user.id, target);
      if (code) return error(res, code === 'NOT_FOUND' ? 404 : 409, code);
      json(res, 200, target === 'RETURNED' ? { ...loan, returned_by_username: user.username } : loan);
    },
  };
  const availabilityRoute = {
    roles: loanRoles,
    async handle(_req, res, _session, { id, query }) {
      const input = availabilityInput(id, query);
      if (!input) return error(res, 400, 'INVALID_INPUT');
      const { equipmentId, from, to } = input;
      const rows = await store.readAvailability(equipmentId, from, to);
      const asOf = new Date(now()).toISOString();
      if (!rows.length) return error(res, 404, 'NOT_FOUND');
      json(res, 200, {
        equipment_id: equipmentId,
        timezone: 'Asia/Bangkok',
        as_of: asOf,
        available: availableSlots(from, to, rows),
      });
    },
  };

  async function login(req, res) {
    if (req.headers.origin !== origin) return error(res, 403, 'ORIGIN_FORBIDDEN');
    const seconds = loginRetryAfter(clientAddress(req, trustedProxyIp));
    if (seconds) {
      res.setHeader('Retry-After', seconds);
      return error(res, 429, 'LOGIN_RATE_LIMITED');
    }
    const input = await credentials(req);
    if (!input) return error(res, 400, 'INVALID_INPUT');
    const user = await store.userByUsername(input.username);
    const valid = await verifyPassword(input.password, user?.password_hash ?? dummyHash);
    if (!user || !valid) return error(res, 401, 'INVALID_CREDENTIALS');

    const token = randomBytes(32).toString('base64url');
    await store.createSession(sessionHash(token), user.id);
    res.setHeader('Set-Cookie', cookieName + '=' + token + '; Max-Age=' + sessionSeconds + '; ' + cookieAttributes);
    json(res, 200, identity(user, csrfToken(token)));
  }

  async function register(req, res) {
    if (req.headers.origin !== origin) return error(res, 403, 'ORIGIN_FORBIDDEN');
    const seconds = registerRetryAfter(clientAddress(req, trustedProxyIp));
    if (seconds) {
      res.setHeader('Retry-After', seconds);
      return error(res, 429, 'REGISTER_RATE_LIMITED');
    }
    const input = await registrationInput(req);
    if (!input) return error(res, 400, 'INVALID_INPUT');
    const { username, password } = input;
    if (!await store.createMember(username, await hashPassword(password))) {
      return error(res, 409, 'USERNAME_TAKEN');
    }
    json(res, 201, { username, role: 'MEMBER' });
  }

  return async (req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    try {
      const { pathname, searchParams } = new URL(req.url, origin);
      const key = req.method + ' ' + pathname;
      if (key === 'POST /auth/login') return await login(req, res);
      if (key === 'POST /auth/register') return await register(req, res);

      const availability = /^GET \/equipment\/([^/]+)\/availability$/.exec(key);
      const loanDetail = /^GET \/loan-requests\/([^/]+)$/.exec(key);
      const decision = /^POST \/loan-requests\/([^/]+)\/(approve|reject|handover|return)$/.exec(key);
      const route = availability ? availabilityRoute : loanDetail ? loanDetailRoute
        : decision ? loanDecisionRoute : protectedRoutes.get(key);
      if (!route) return error(res, 404, 'NOT_FOUND');

      const token = sessionToken(req);
      const hash = token && sessionHash(token);
      const user = hash && await store.userBySession(hash);
      if (!user) return error(res, 401, 'AUTH_REQUIRED');
      if (route.role && user.role !== route.role) return error(res, 403, 'FORBIDDEN');
      if (route.roles && !route.roles.has(user.role)) return error(res, 403, 'FORBIDDEN');
      const csrf = csrfToken(token);
      if (!safeMethods.has(req.method) && !hasValidCsrf(req, csrf)) return error(res, 403, 'CSRF_INVALID');
      const session = { user: identity(user, csrf), hash };
      const match = availability ?? loanDetail ?? decision;
      await route.handle(req, res, session, { id: match?.[1], action: decision?.[2], query: searchParams });
    } catch (cause) {
      logger.error('Lending API request failed', cause.code ?? cause.name);
      if (res.headersSent) return res.destroy();
      error(res, 500, 'INTERNAL_ERROR');
    }
  };
}
