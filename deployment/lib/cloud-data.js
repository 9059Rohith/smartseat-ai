const { engineRequest } = require('./cloud-auth');
const lastSync = new Map();

function offlineState(snapshot, syncedAt) {
  const data = snapshot || { tables: [], cameras: [], queue: [], reservations: [], events: [], demo: false };
  return { ...data, now: Date.now() / 1000, engine_connected: false, cloud_saved_at: syncedAt || null,
    tables: data.tables.map(row => ({ ...row, display: 'unknown', observed: false, surface: { state: 'unknown', at: null, items: [] } })),
    cameras: data.cameras.map(row => ({ ...row, status: 'reconnecting', image: false, detected_tables: [], people: 0, chairs: 0,
      message: 'Restaurant engine is offline. This is the last saved workspace.' })),
  };
}
async function floor(req, context, restaurant) {
  let current;
  if (context.jar.smartseat_session) {
    try {
      const response = await engineRequest(req, 'state');
      if (response.ok) current = await response.json();
    } catch { /* Cached records remain private and explicitly offline. */ }
  }
  if (current) {
    let saved = null;
    if (Date.now() - (lastSync.get(restaurant.id) || 0) > 15000) {
      const at = new Date().toISOString();
      const result = await context.supabase.from('smartseat_floor_cache').upsert({ workspace_id: restaurant.id,
        payload: current, source_at: new Date(current.now * 1000).toISOString(), updated_at: at });
      if (!result.error) { lastSync.set(restaurant.id, Date.now()); saved = at; }
    } else saved = new Date(lastSync.get(restaurant.id)).toISOString();
    return { ...current, engine_connected: true, cloud_saved_at: saved };
  }
  const cached = await context.supabase.from('smartseat_floor_cache').select('payload,source_at').eq('workspace_id', restaurant.id).maybeSingle();
  if (cached.error) throw cached.error;
  return { ...offlineState(cached.data?.payload, cached.data?.source_at), engine_paired: Boolean(context.jar.smartseat_session) };
}
async function report(req, context, restaurant) {
  const incoming = new URL(req.url, 'https://gateway.invalid');
  incoming.searchParams.delete('route');
  const period = incoming.searchParams.get('period') || 'custom';
  if (!['today','yesterday','week','thisweek','lastweek','weekend','month','custom'].includes(period)) {
    return { status: 400, data: { detail: 'Choose a valid report period.' } };
  }
  if (context.jar.smartseat_session) {
    try {
      const response = await engineRequest(req, 'analytics?' + incoming.searchParams.toString());
      if (response.ok) {
        const data = await response.json(), at = new Date().toISOString();
        const result = await context.supabase.from('smartseat_report_cache').upsert({ workspace_id: restaurant.id, period,
          payload: data, source_at: at, updated_at: at });
        const rows = data.daily.map(day => ({ workspace_id: restaurant.id, period, day: day.date, visits: day.seatings,
          known_guests: day.guests, occupancy: day.occupancy, turnover: day.turnover, confirmed_cleanings: day.cleaned, source_at: at }));
        if (rows.length) await context.supabase.from('smartseat_daily_metrics').upsert(rows);
        return { status: 200, data: { ...data, cached: false, synced_at: result.error ? null : at } };
      }
      if (response.status !== 401 && response.status < 500) return { status: response.status, data: await response.json() };
    } catch { /* Fall through to an actual previously saved report. */ }
  }
  const cached = await context.supabase.from('smartseat_report_cache').select('payload,source_at').eq('workspace_id', restaurant.id).eq('period', period).maybeSingle();
  if (cached.error) throw cached.error;
  if (!cached.data) return { status: 409, data: { detail: 'Connect your restaurant engine in Account to collect real owner reports. No saved report is available yet.' } };
  return { status: 200, data: { ...cached.data.payload, cached: true, synced_at: cached.data.source_at } };
}
module.exports = { floor, report, offlineState };
