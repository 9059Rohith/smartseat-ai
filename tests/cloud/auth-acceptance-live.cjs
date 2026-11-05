// Safe deployed checks: no credentials, emails, accounts or restaurant records created.
const assert = require('node:assert/strict');
const origin = process.env.SMARTSEAT_ACCEPTANCE_ORIGIN || 'https://smartseat-ai-9059.vercel.app';
const payload = Buffer.from(JSON.stringify({ sub: '11111111-1111-4111-8111-111111111111', exp: 1 })).toString('base64url');
const session = { access_token: 'eyJhbGciOiJIUzI1NiJ9.' + payload + '.invalid-proof', refresh_token: 'invalid-test-refresh',
  expires_at: 1, expires_in: 3600, token_type: 'bearer', user: { id: '11111111-1111-4111-8111-111111111111', aud: 'authenticated' } };
const staleCookie = 'smartseat-cloud-auth=base64-' + Buffer.from(JSON.stringify(session)).toString('base64url');

async function check(label, path, options, expected) {
  const res = await fetch(origin + path, { redirect: 'manual', signal: AbortSignal.timeout(20000), ...options });
  assert.equal(res.status, expected, label);
  assert.match(res.headers.get('cache-control'), /no-store/, label);
  const body = await res.text();
  assert.doesNotMatch(body, /access_token|refresh_token|service_role|stack|traceback/i, label);
  console.log(label + ': HTTP ' + res.status);
  return { res, body };
}
(async () => {
  const config = await check('Public provider configuration', '/api/auth/config', {}, 200);
  assert.equal(JSON.parse(config.body).enabled, true);
  assert.equal(JSON.parse(config.body).google_enabled, true);
  const anonymous = await check('Missing session', '/api/me', {}, 200);
  assert.equal(JSON.parse(anonymous.body), null);
  await check('Anonymous private account', '/api/auth/account', {}, 401);
  await check('Anonymous restaurant state', '/api/state', {}, 401);
  const stale = await check('Expired session and invalid refresh', '/api/auth/account', { headers: { cookie: staleCookie } }, 401);
  assert.match(stale.res.headers.get('set-cookie') || '', /smartseat-cloud-auth=;[^,]*Max-Age=0/);
  const confirmation = await check('Missing confirmation token', '/api/auth/confirm?type=recovery', {}, 303);
  assert.equal(confirmation.res.headers.get('location'), '/?auth_error=confirmation_failed');
  const signup = await check('Invalid signup has no account/email side effect', '/api/auth/sign-up', {
    method: 'POST', headers: { origin, 'content-type': 'application/json' }, body: JSON.stringify({ email: 'invalid', password: 'short', name: 'Test' }),
  }, 400);
  assert.match(JSON.parse(signup.body).detail, /valid email/i);
})().catch(error => { console.error(error.message); process.exitCode = 1; });
