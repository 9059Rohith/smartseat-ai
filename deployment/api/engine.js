// Authenticated same-origin gateway. Camera inference and SQLite stay on premises.
const cloud = require('../lib/cloud-auth');
const cloudData = require('../lib/cloud-data');
const guard = require('../lib/abuse').createGuard();
module.exports = async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  const route = Array.isArray(req.query.route) ? req.query.route.join('/') : req.query.route || '';
  if (!/^[a-zA-Z0-9_/-]+$/.test(route) || route.includes('..') || route === 'live') {
    return res.status(404).json({ detail: 'Use the authenticated state endpoint for live updates.' });
  }
  try {
    if (cloud.enabled() && !['GET','HEAD'].includes(req.method) && req.headers.origin !== cloud.site()) {
      return res.status(403).json({ detail: 'Open SmartSeat directly to perform this action.' });
    }
    const rejected=guard(req,route);
    if(rejected){
      if(rejected.retryAfter)res.setHeader('Retry-After',String(rejected.retryAfter));
      return res.status(rejected.status).json({detail:rejected.detail});
    }
    if (route === 'auth/config') {
      let google = false;
      if (cloud.enabled()) {
        try {
          const response = await fetch(new URL('/auth/v1/settings', process.env.SUPABASE_URL), {
            headers: { apikey: process.env.SUPABASE_PUBLISHABLE_KEY }, signal: AbortSignal.timeout(6000) });
          if (response.ok) google = Boolean((await response.json()).external?.google);
        } catch { /* An unavailable provider is never advertised as working. */ }
      }
      return res.json({ enabled: cloud.enabled(), google_enabled: google });
    }
    if (cloud.enabled()) {
      const context = cloud.createContext(req, res);
      if (route === 'health') return res.json({ ok: true, demo: false, cloud_auth: true });
      if (route.startsWith('auth/') || route === 'logout') return await cloud.handleAuth(req, res, route, context);
      const user = await cloud.identity(context);
      if (!user) return route === 'me' ? res.json(null) : res.status(401).json({ detail: 'Sign in to SmartSeat.' });
      const restaurant = await cloud.workspace(context, user);
      if (route === 'me') {
        let engineUser;
        if (context.jar.smartseat_session) {
          try { const result = await cloud.engineRequest(req, 'me'); if (result.ok) engineUser = await result.json(); } catch { /* Engine access is separate. */ }
        }
        return res.json(cloud.publicUser(user, restaurant, engineUser?.role, Boolean(engineUser)));
      }
      if (route === 'state') return res.json(await cloudData.floor(req, context, restaurant));
      if (route === 'analytics') { const result = await cloudData.report(req, context, restaurant); return res.status(result.status).json(result.data); }
      if (route === 'login' || !context.jar.smartseat_session) return res.status(403).json({ detail: 'Connect your restaurant engine from Account first.' });
    }
    const upstream = cloud.engineURL(route);
    const incoming = new URL(req.url, 'https://gateway.invalid');
    incoming.searchParams.delete('route');
    upstream.search = incoming.searchParams.toString();
    const headers = { 'ngrok-skip-browser-warning': 'true', 'User-Agent': 'SmartSeat-Gateway/1.0' };
    for (const key of ['cookie', 'origin', 'content-type', 'accept']) {
      if (req.headers[key]) headers[key] = req.headers[key];
    }
    if (cloud.enabled()) headers.cookie = cloud.engineCookie(req);
    if(process.env.SMARTSEAT_RUNTIME==='local')headers['x-forwarded-proto']='https';
    const body = ['GET', 'HEAD'].includes(req.method) || req.body === undefined ? undefined :
      typeof req.body === 'string' || Buffer.isBuffer(req.body) ? req.body : JSON.stringify(req.body);
    const response = await fetch(upstream, { method: req.method, headers, body,
      redirect: 'manual', signal: AbortSignal.timeout(15000) });
    const type = response.headers.get('content-type') || 'application/octet-stream';
    if (response.status >= 400 && !type.includes('application/json')) throw new Error('Engine unavailable');
    const content = Buffer.from(await response.arrayBuffer());
    const cookies = response.headers.getSetCookie();
    if (cookies.length) cloud.appendCookies(res, cookies);
    res.setHeader('Content-Type', type);
    return res.status(response.status).send(content);
  } catch {
    return res.status(502).json({ detail: 'Restaurant engine is offline. Keep the restaurant computer and its public connector running.' });
  }
};
