const { test } = require('node:test');
const assert = require('node:assert/strict');
const cloud = require('../../deployment/lib/cloud-auth');

function response() {
  const headers = new Map();
  return { statusCode: 200, headers, getHeader: key => headers.get(key),
    setHeader(key, value) { headers.set(key, value); },
    status(code) { this.statusCode = code; return this; },
    json(body) { this.body = body; return this; },
    redirect(code, location) { this.statusCode = code; this.location = location; return this; } };
}
function provider(t, handler) {
  const oldFetch = global.fetch;
  const oldEnv = { ...process.env };
  process.env.SUPABASE_URL = 'https://auth-acceptance.example.invalid';
  process.env.SUPABASE_PUBLISHABLE_KEY = 'test-publishable-key';
  process.env.SMARTSEAT_CLOUD_AUTH = '1';
  global.fetch = async (url, options = {}) => handler(new URL(url.url || url), options);
  t.after(() => { global.fetch = oldFetch; process.env = oldEnv; });
}
const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', 'x-supabase-api-version': '2024-01-01' } });
function request(route, body, cookie = '') {
  return { method: 'POST', url: '/api/' + route, query: { route }, headers: { origin: cloud.site(), cookie }, body };
}
async function action(req, res, route) { return cloud.handleAuth(req, res, route, cloud.createContext(req, res)); }

test('recovery provider failure is unavailable rather than a false delivery confirmation', async t => {
  provider(t, () => json(400, { code: 'email_address_not_authorized', msg: 'Email address not authorized' }));
  const res = response();
  await action(request('auth/forgot-password', { email: 'owner@example.invalid' }), res, 'auth/forgot-password');
  assert.equal(res.statusCode, 503);
  assert.match(res.body.detail, /unavailable/i);
  assert.doesNotMatch(JSON.stringify(res.body), /sent|authorized|owner@example/i);
});

test('recovery rate limiting remains explicit without exposing account existence', async t => {
  provider(t, () => json(429, { code: 'over_email_send_rate_limit', msg: 'Email rate limit exceeded' }));
  const res = response();
  await action(request('auth/forgot-password', { email: 'owner@example.invalid' }), res, 'auth/forgot-password');
  assert.equal(res.statusCode, 429);
  assert.match(res.body.detail, /try again later/i);
});

test('accepted recovery keeps the PKCE verifier secure and account existence private', async t => {
  provider(t, (url, options) => {
    assert.equal(url.pathname, '/auth/v1/recover');
    assert.equal(url.searchParams.get('redirect_to'), cloud.site() + '/api/auth/callback?recovery=1');
    const body = JSON.parse(options.body);
    assert.ok(body.code_challenge);
    assert.equal(body.code_challenge_method, 's256');
    return json(200, {});
  });
  const res = response();
  await action(request('auth/forgot-password', { email: 'owner@example.invalid' }), res, 'auth/forgot-password');
  assert.equal(res.statusCode, 200);
  assert.match(res.body.message, /^If this account exists/);
  const cookies = res.headers.get('Set-Cookie');
  assert.ok(cookies.some(value => /code-verifier=/.test(value)));
  for (const value of cookies) { assert.match(value, /HttpOnly/); assert.match(value, /Secure/); assert.match(value, /SameSite=Lax/); }
});

test('invalid sign-up input is rejected before sending email or creating an account', async t => {
  provider(t, () => { throw new Error('Invalid sign-up must not reach the provider'); });
  const res = response();
  await action(request('auth/sign-up', { email: 'invalid', password: 'short', name: 'Test' }), res, 'auth/sign-up');
  assert.equal(res.statusCode, 400);
});

test('provider-restricted sign-up fails honestly without disclosing provider details', async t => {
  provider(t, () => json(400, { code: 'email_address_not_authorized', msg: 'Email address not authorized' }));
  const res = response();
  await action(request('auth/sign-up', { email: 'owner@example.invalid', password: 'test-password-long', name: 'Test' }), res, 'auth/sign-up');
  assert.equal(res.statusCode, 400);
  assert.doesNotMatch(JSON.stringify(res.body), /check your email|authorized|owner@example/i);
});

test('unverified email accounts cannot sign in and receive a verification prompt', async t => {
  provider(t, () => json(400, { code: 'email_not_confirmed', msg: 'Email not confirmed' }));
  const res = response();
  await action(request('auth/sign-in', { email: 'owner@example.invalid', password: 'test-password-long' }), res, 'auth/sign-in');
  assert.equal(res.statusCode, 401);
  assert.match(res.body.detail, /verify your email/i);
});

test('expired confirmation links return a safe failure without a session', async t => {
  provider(t, () => json(403, { code: 'otp_expired', msg: 'Token has expired or is invalid' }));
  const req = { method: 'GET', headers: {}, query: { token_hash: 'expired-test-proof', type: 'recovery' } };
  const res = response();
  await action(req, res, 'auth/confirm');
  assert.equal(res.statusCode, 303);
  assert.equal(res.location, '/?auth_error=confirmation_failed');
});

function sessionCookie(expiresAt) {
  const payload = Buffer.from(JSON.stringify({ sub: '11111111-1111-4111-8111-111111111111', exp: expiresAt })).toString('base64url');
  const session = { access_token: 'eyJhbGciOiJIUzI1NiJ9.' + payload + '.invalid-proof', refresh_token: 'invalid-test-refresh',
    expires_at: expiresAt, expires_in: 3600, token_type: 'bearer', user: { id: '11111111-1111-4111-8111-111111111111', aud: 'authenticated', role: 'authenticated' } };
  return 'smartseat-cloud-auth=base64-' + Buffer.from(JSON.stringify(session)).toString('base64url');
}

test('expired session with a rejected refresh is cleared and cannot access private state', async t => {
  t.mock.method(console, 'error', () => {}); // The SDK logs this expected refresh rejection.
  t.mock.method(console, 'warn', () => {});
  provider(t, (url) => {
    assert.equal(url.pathname, '/auth/v1/token');
    assert.equal(url.searchParams.get('grant_type'), 'refresh_token');
    return json(400, { code: 'refresh_token_not_found', msg: 'Invalid Refresh Token: Refresh Token Not Found' });
  });
  const req = request('state', undefined, sessionCookie(1)); req.method = 'GET';
  const res = response();
  await require('../../deployment/api/engine')(req, res);
  assert.equal(res.statusCode, 401);
  assert.match(res.body.detail, /sign in/i);
  const cookies = res.headers.get('Set-Cookie') || [];
  assert.ok(cookies.some(value => /^smartseat-cloud-auth=;/.test(value) && /Max-Age=0/.test(value)));
  assert.equal(res.headers.get('Cache-Control'), 'no-store');
});

test('a locally unexpired forged session is validated by the provider before account access', async t => {
  provider(t, url => {
    assert.equal(url.pathname, '/auth/v1/user');
    return json(401, { code: 'bad_jwt', msg: 'Invalid JWT' });
  });
  const req = request('auth/account', undefined, sessionCookie(Math.floor(Date.now() / 1000) + 3600)); req.method = 'GET';
  const res = response();
  await action(req, res, 'auth/account');
  assert.equal(res.statusCode, 401);
  assert.match(res.body.detail, /sign in/i);
});

test('anonymous managed sessions cannot read owner accounts', async () => {
  const res = response();
  await cloud.handleAuth(request('auth/account'), res, 'auth/account', {
    supabase: { auth: { getUser: async () => ({ data: { user: { id: 'anonymous-proof', is_anonymous: true } }, error: null }) } },
  });
  assert.equal(res.statusCode, 401);
});

test('expired access tokens refresh through secure response cookies before returning validated identity', async t => {
  const user = { id: '11111111-1111-4111-8111-111111111111', aud: 'authenticated', role: 'authenticated',
    email: 'owner@example.invalid', email_confirmed_at: '2026-11-05T00:00:00Z', is_anonymous: false };
  const payload = Buffer.from(JSON.stringify({ sub: user.id, exp: Math.floor(Date.now() / 1000) + 3600 })).toString('base64url');
  provider(t, url => {
    if (url.pathname === '/auth/v1/token') return json(200, { access_token: 'eyJhbGciOiJIUzI1NiJ9.' + payload + '.test-proof',
      refresh_token: 'rotated-test-refresh', token_type: 'bearer', expires_in: 3600, user });
    assert.equal(url.pathname, '/auth/v1/user');
    return json(200, user);
  });
  const req = request('auth/account', undefined, sessionCookie(1));
  const res = response();
  const result = await cloud.identity(cloud.createContext(req, res));
  assert.equal(result.id, user.id);
  const cookies = res.headers.get('Set-Cookie') || [];
  assert.ok(cookies.some(value => /^smartseat-cloud-auth=base64-/.test(value)));
  for (const value of cookies) { assert.match(value, /HttpOnly/); assert.match(value, /Secure/); assert.match(value, /SameSite=Lax/); }
});

test('password updates require a validated identity before any password change', async t => {
  provider(t, () => { throw new Error('Missing sessions must not reach password update'); });
  const res = response();
  await action(request('auth/update-password', { password: 'test-password-long' }), res, 'auth/update-password');
  assert.equal(res.statusCode, 401);
});
