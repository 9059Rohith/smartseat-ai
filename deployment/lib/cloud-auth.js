const { createServerClient } = require('@supabase/ssr');
const cookie = require('cookie');

const enabled = () => process.env.SMARTSEAT_CLOUD_AUTH === '1';
const site = () => (process.env.SMARTSEAT_PUBLIC_ORIGIN || 'https://smartseat-ai-9059.vercel.app').replace(/\/$/, '');

function appendCookies(res, values) {
  const prior = res.getHeader('Set-Cookie') || [];
  res.setHeader('Set-Cookie', [...(Array.isArray(prior) ? prior : [prior]), ...values]);
}
function clearEngine(res) {
  appendCookies(res, [cookie.serialize('smartseat_session', '', { path: '/', secure: true, httpOnly: true, sameSite: 'strict', maxAge: 0 })]);
}
function createContext(req, res) {
  const jar = cookie.parse(req.headers.cookie || '');
  const supabase = createServerClient(process.env.SUPABASE_URL, process.env.SUPABASE_PUBLISHABLE_KEY, {
    cookieOptions: { name: 'smartseat-cloud-auth', path: '/', secure: true, httpOnly: true, sameSite: 'lax' },
    cookies: {
      getAll: () => Object.entries(jar).map(([name, value]) => ({ name, value })),
      setAll(values) {
        values.forEach(({ name, value }) => { jar[name] = value; });
        appendCookies(res, values.map(({ name, value, options }) => cookie.serialize(name, value, {
          ...options, path: '/', secure: true, httpOnly: true, sameSite: 'lax',
        })));
      },
    },
  });
  return { supabase, jar };
}
async function identity(context) {
  const { data, error } = await context.supabase.auth.getUser();
  if (error || !data.user || data.user.is_anonymous) return null;
  return data.user;
}
async function workspace(context, user) {
  const db = context.supabase;
  let result = await db.from('smartseat_workspaces').select('id,name,timezone,owner_id,created_at').eq('owner_id', user.id).maybeSingle();
  if (result.error) throw result.error;
  if (!result.data) {
    const created = await db.rpc('smartseat_create_workspace', { workspace_name: 'Your restaurant' });
    if (created.error) throw created.error;
    result = await db.from('smartseat_workspaces').select('id,name,timezone,owner_id,created_at').eq('id', created.data).single();
    if (result.error) throw result.error;
  }
  const profile = await db.from('smartseat_profiles').select('display_name').eq('user_id', user.id).maybeSingle();
  if (profile.error) throw profile.error;
  const displayName = String(profile.data?.display_name || user.user_metadata?.full_name || user.email?.split('@')[0] || 'Owner').slice(0, 100);
  if (!profile.data) {
    const saved = await db.from('smartseat_profiles').upsert({ user_id: user.id, display_name: displayName }, { ignoreDuplicates: true });
    if (saved.error) throw saved.error;
  }
  return { ...result.data, display_name: displayName };
}
function publicUser(user, restaurant, engineRole, connected = false) {
  return { id: user.id, name: restaurant.display_name, email: user.email, role: engineRole || 'owner', cloud: true,
    engine_access: connected, workspace: { id: restaurant.id, name: restaurant.name, timezone: restaurant.timezone },
    email_verified: Boolean(user.email_confirmed_at), provider: user.app_metadata?.provider || 'email' };
}
async function audit(context, restaurant, event) {
  const result = await context.supabase.rpc('smartseat_record_event', { target: restaurant?.id || null, event_name: event });
  if (result.error) console.warn('Cloud audit could not be recorded:', result.error.code);
}
function engineURL(path) {
  const origin = new URL((process.env.SMARTSEAT_ENGINE_ORIGIN || '').trim());
  if (origin.protocol !== 'https:' || origin.username || origin.password || origin.search || origin.hash) throw new Error('Invalid engine configuration');
  origin.pathname = origin.pathname.replace(/\/$/, '') + '/';
  return new URL('api/' + path, origin);
}
async function engineRequest(req, path, options = {}) {
  return fetch(engineURL(path), { ...options, redirect: 'manual', signal: AbortSignal.timeout(8000), headers: {
    'ngrok-skip-browser-warning': 'true', 'User-Agent': 'SmartSeat-Gateway/1.0', cookie: engineCookie(req),
    ...(req.headers.origin ? { origin: req.headers.origin } : {}), ...options.headers,
  } });
}
function engineCookie(req) {
  const session = cookie.parse(req.headers.cookie || '').smartseat_session;
  return session ? cookie.serialize('smartseat_session', session) : '';
}
async function disconnect(req, res) {
  if (engineCookie(req)) {
    try { await engineRequest(req, 'logout', { method: 'POST' }); } catch { /* The engine may be offline. */ }
  }
  clearEngine(res);
}
function input(req) {
  if (req.body && typeof req.body === 'object') return req.body;
  try { return JSON.parse(req.body || '{}'); } catch { return {}; }
}
function email(value) { return typeof value === 'string' && value.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value); }
function password(value) { return typeof value === 'string' && value.length >= 12 && value.length <= 128; }

async function handleAuth(req, res, route, context) {
  const db = context.supabase, body = input(req);
  const fail = (status, detail) => res.status(status).json({ detail });
  if (route === 'auth/google' && req.method === 'GET') {
    const result = await db.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: site() + '/api/auth/callback', skipBrowserRedirect: true } });
    if (result.error || !result.data.url) return res.redirect(303, '/?auth_error=google_unavailable');
    return res.redirect(303, result.data.url);
  }
  if (route === 'auth/callback' && req.method === 'GET') {
    const code = req.query.code;
    const result = typeof code === 'string' ? await db.auth.exchangeCodeForSession(code) : { error: true };
    if (result.error) return res.redirect(303, '/?auth_error=callback_failed');
    await disconnect(req, res);
    const user = await identity(context);
    if (user) { const restaurant = await workspace(context, user); await audit(context, restaurant, 'signed_in'); }
    return res.redirect(303, req.query.recovery === '1' ? '/?reset_password=1' : '/');
  }
  if (route === 'auth/confirm' && req.method === 'GET') {
    const { token_hash, type } = req.query;
    if (typeof token_hash !== 'string' || !['signup', 'recovery', 'email_change'].includes(type)) return res.redirect(303, '/?auth_error=confirmation_failed');
    const result = await db.auth.verifyOtp({ token_hash, type });
    if (result.error) return res.redirect(303, '/?auth_error=confirmation_failed');
    await disconnect(req, res);
    return res.redirect(303, type === 'recovery' ? '/?reset_password=1' : '/');
  }
  if (req.method === 'POST' && route === 'auth/sign-in') {
    if (!email(body.email) || typeof body.password !== 'string' || body.password.length > 128) return fail(400, 'Enter your email and password.');
    const result = await db.auth.signInWithPassword({ email: body.email.trim(), password: body.password });
    if (result.error) return fail(401, result.error.code === 'email_not_confirmed' ? 'Verify your email before signing in.' : 'The email or password is incorrect.');
    await disconnect(req, res);
    const user = await identity(context), restaurant = await workspace(context, user);
    await audit(context, restaurant, 'signed_in');
    return res.json(publicUser(user, restaurant));
  }
  if (req.method === 'POST' && route === 'auth/sign-up') {
    if (!email(body.email) || !password(body.password) || typeof body.name !== 'string' || !body.name.trim() || body.name.length > 100) return fail(400, 'Enter your name, valid email and a password of 12–128 characters.');
    const result = await db.auth.signUp({ email: body.email.trim(), password: body.password,
      options: { data: { full_name: body.name.trim() }, emailRedirectTo: site() + '/api/auth/callback' } });
    if (result.error) return fail(result.error.status === 429 ? 429 : 400, result.error.status === 429 ? 'Too many attempts. Please try again later.' : 'Account creation could not be completed. Check your details and try again.');
    if (result.data.session) {
      await disconnect(req, res);
      const user = await identity(context), restaurant = await workspace(context, user);
      return res.json({ user: publicUser(user, restaurant) });
    }
    return res.json({ message: 'Check your email to verify your account, then return here to sign in.' });
  }
  if (req.method === 'POST' && route === 'auth/forgot-password') {
    if (!email(body.email)) return fail(400, 'Enter a valid email address.');
    const result = await db.auth.resetPasswordForEmail(body.email.trim(), { redirectTo: site() + '/api/auth/callback?recovery=1' });
    if (result.error?.status === 429) return fail(429, 'Too many requests. Please try again later.');
    if (result.error) return fail(503, 'Email recovery is temporarily unavailable. Please try again later.');
    return res.json({ message: 'If this account exists, a password reset link has been sent.' });
  }
  const user = await identity(context);
  if (!user) return fail(401, 'Sign in to your SmartSeat account.');
  const restaurant = await workspace(context, user);
  if (req.method === 'POST' && (route === 'auth/sign-out' || route === 'logout')) {
    await audit(context, restaurant, 'signed_out'); await disconnect(req, res); await db.auth.signOut({ scope: 'local' });
    return res.json({ ok: true });
  }
  if (req.method === 'POST' && route === 'auth/update-password') {
    if (!password(body.password)) return fail(400, 'Use a password of 12–128 characters.');
    const result = await db.auth.updateUser({ password: body.password });
    if (result.error) return fail(400, 'The password could not be updated. Try requesting another reset link.');
    return res.json({ message: 'Password updated.' });
  }
  if (req.method === 'GET' && route === 'auth/account') {
    const events = await db.from('smartseat_audit_events').select('event,created_at').eq('workspace_id', restaurant.id).order('created_at', { ascending: false }).limit(12);
    return res.json({ user: publicUser(user, restaurant, undefined, Boolean(context.jar.smartseat_session)), events: events.data || [] });
  }
  if (req.method === 'POST' && route === 'auth/update-account') {
    const name = String(body.name || '').trim(), workspaceName = String(body.workspace_name || '').trim();
    if (!name || name.length > 100 || !workspaceName || workspaceName.length > 100) return fail(400, 'Use names of 1–100 characters.');
    const profile = await db.from('smartseat_profiles').upsert({ user_id: user.id, display_name: name });
    const updated = await db.from('smartseat_workspaces').update({ name: workspaceName, updated_at: new Date().toISOString() }).eq('id', restaurant.id);
    if (profile.error || updated.error) return fail(400, 'Account details could not be saved.');
    await audit(context, restaurant, 'workspace_updated');
    return res.json(publicUser(user, { ...restaurant, name: workspaceName, display_name: name }, undefined, Boolean(context.jar.smartseat_session)));
  }
  if (req.method === 'POST' && route === 'auth/connect-engine') {
    if (typeof body.name !== 'string' || !body.name.trim() || typeof body.password !== 'string' || body.password.length > 160) return fail(400, 'Enter your restaurant engine username and password.');
    try {
      const health = await engineRequest({ headers: {} }, 'health');
      if (!health.ok || (await health.json()).app !== 'smartseat') return fail(502, 'This connector is not serving SmartSeat. Start the dedicated restaurant engine.');
      const response = await engineRequest(req, 'login', { method: 'POST', headers: { 'content-type': 'application/json', origin: site() }, body: JSON.stringify({ name: body.name, password: body.password }) });
      if (response.status === 401) return fail(401, 'Restaurant engine credentials are incorrect.');
      if (!response.ok) return fail(502, 'The restaurant engine could not connect. Keep the restaurant computer online.');
      const engineUser = await response.json();
      appendCookies(res, response.headers.getSetCookie());
      await audit(context, restaurant, 'engine_connected');
      return res.json(publicUser(user, restaurant, engineUser.role, true));
    } catch { return fail(502, 'Restaurant engine is unavailable. Keep the restaurant computer and connector running.'); }
  }
  if (req.method === 'POST' && route === 'auth/disconnect-engine') {
    await disconnect(req, res); return res.json(publicUser(user, restaurant));
  }
  return fail(404, 'This account action is not available.');
}

module.exports = { enabled, site, createContext, identity, workspace, publicUser, handleAuth, appendCookies, engineRequest, engineURL, engineCookie, audit };
