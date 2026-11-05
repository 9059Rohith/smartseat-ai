import React, { useEffect, useRef, useState } from 'react'
import { Button, Empty, Icon, Status, cameraLabels, duration, eventLabels, stamp } from './ui'

const surfaceLabels = {items_present:'Items remain · check table',looks_clear:'Looks clear · confirm cleaning',occupied:'In use',unknown:'Surface not verified'}
export function SurfaceCheck({ surface }) {
  const [,expire]=useState(0)
  useEffect(()=>{
    if(!surface?.at)return
    const timer=setTimeout(()=>expire(value=>value+1),Math.max(0,(surface.at+5-Date.now()/1000)*1000)+50)
    return()=>clearTimeout(timer)
  },[surface?.at])
  const age=surface?.at ? Date.now()/1000-surface.at : Infinity
  const fresh=age>=0 && age<=5
  const state=fresh ? surface.state : 'unknown'
  const items=fresh && surface.items?.length ? [...new Set(surface.items.map(item=>item.label))].join(', ') : ''
  return <span className={'surface-note '+state} title={items || 'Visual clearance is not a sanitation check. Staff confirm actual cleaning.'}><i className="dot"/>{surfaceLabels[state]}{items && <span> · {items}</span>}</span>
}

export function TableActions({ table, act }) {
  const items = table.display === 'available' ? [['occupy', 'Mark occupied']] :
    table.state === 'cleaning' ? [['clean', 'Mark cleaned']] :
    ['occupied', 'waiting'].includes(table.state) ?
      [...(table.greeted ? [] : [['greet', 'Confirm greeting']]), ['depart', 'Mark departed']] : []
  return <div className="actions">{items.map(([action, label]) =>
    <Button key={action} variant={action === 'clean' || table.state === 'waiting' && action === 'greet' ? 'primary compact' : 'compact'} onClick={() => act('/tables/' + table.id + '/' + action, 'POST', undefined, label + ' saved.')}>{label}</Button>
  )}</div>
}

export function CameraFeed({ camera, raw = false, fixedFrame, children }) {
  const url = camera?.image && '/api/cameras/' + camera.id + '/frame?' + (raw ? 'raw=true&' : '') + 'v=' + (fixedFrame || camera.frame_at)
  return url ? <div className="feed-image"><img src={url} alt={raw ? 'Unannotated camera frame for drawing zones' : 'Camera view with anonymous detections and table outlines'} draggable="false"/>{!raw && camera.status==='obscured' && <div className="feed-condition"><Icon name="camera" size={34}/><strong>View blocked or dark</strong><span>Uncover the lens and improve lighting.</span></div>}{children}</div> :
    <div className="feed-empty"><Icon name="camera" size={40}/><strong>{camera ? cameraLabels[camera.status] : 'No camera selected'}</strong><span>{camera?.message || 'Add a camera to view your dining room.'}</span></div>
}

export function DetectedTables({ camera, onMap }) {
  if (!camera || camera.status !== 'live') return null
  const scan = camera.table_scan
  const scanText = !scan ? '' : scan.status === 'loading' ? 'Loading the local broad table model…' :
    scan.status === 'error' ? 'Broad table scan failed. Restart the camera and check the local model installation.' :
    scan.status === 'unavailable' ? 'Broad table model is not installed. Run the setup launcher.' :
    scan.matched ? `Broad table scan: ${Math.max(0, Date.now()/1000-scan.at).toFixed(0)}s ago · ${(scan.ms/1000).toFixed(1)}s processing` :
    'Scanning this view for tables and desks. Keep the camera steady for several seconds.'
  return <section className="detections">
    <div className="detection-summary"><strong>Detected in the camera</strong><span>{camera.people} {camera.people === 1 ? 'person' : 'people'} · {camera.detected_tables?.length || 0} table candidates · {camera.chairs || 0} chairs</span></div>
    {scanText && <p className="muted" role="status">{scanText}</p>}
    {camera.detected_tables?.length ? <div className="detection-list">{camera.detected_tables.map((item, index) =>
      <div className="detection-row" key={index}><div><strong>{item.method === 'surface_outline' ? 'Table surface candidate' : item.label || 'Dining table'} {index + 1}</strong><small>{Math.round(item.confidence * 100)}% model score{item.method === 'surface_outline' ? ' · visible outline' : ''} · {item.people} overlapping {item.people === 1 ? 'person' : 'people'}</small><SurfaceCheck surface={item.surface} now={Date.now()/1000}/></div>
        {onMap && <Button variant="compact" onClick={() => onMap(item)}>Map this table</Button>}</div>)}</div> :
      <p className="muted">No table candidate detected yet. Keep the table in view while the broad scan runs, or draw its seating zone in Cameras.</p>}
  </section>
}

export function Floor({ state, camera, setCamera, act, manager, navigate, chooseParty, mapTable }) {
  const screen = useRef(null)
  const stats = [
    ['available', 'chair', 'Available'], ['occupied', 'people', 'Occupied'], ['waiting', 'bell', 'Needs service'], ['cleaning', 'clean', 'Needs cleaning'],
  ]
  const attention = state.tables.filter(t => ['waiting', 'cleaning'].includes(t.state))
  const live = camera?.status === 'live'
  const cameraStats = [
    ['People in view', 'people', live ? camera.people : '—'],
    ['Table candidates in view', 'chair', live ? camera.detected_tables?.length || 0 : '—'],
    ['Chairs in view', 'chair', live ? camera.chairs || 0 : '—'],
    ['Mapped tables', 'floor', state.tables.length],
  ]
  return <>
    <div className="metrics live-metrics" aria-label="Live camera statistics" aria-live="polite">
      {cameraStats.map(([label, icon, value]) => <div className="metric" key={label}><Icon name={icon} size={28}/><div><span>{label}</span><strong>{value}</strong></div></div>)}
    </div>
    <div className="stats-caption"><strong>Mapped table workflow</strong><span>Live counts update from the camera. Map a table to start occupancy timers and service statistics.</span></div>
    <div className="metrics workflow-metrics" aria-label="Mapped table statistics">
      {stats.map(([status, icon, label]) => <div className={'metric ' + status} key={status}><Icon name={icon} size={28}/><div><span>{label}</span><strong>{state.tables.filter(t => t.display === status).length}</strong></div></div>)}
    </div>
    <div className="floor-grid">
      <div className="floor-main">
        <section className="panel camera-panel" ref={screen}>
          <div className="panel-head"><h2>Camera floor</h2><div className="actions">
            {state.cameras.length > 0 && <select aria-label="Select camera" value={camera?.id || ''} onChange={e => setCamera(Number(e.target.value))}>{state.cameras.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>}
            {camera && manager && <Button variant="compact" icon={camera.status === 'complete' ? 'replay' : 'camera'} disabled={['starting','stopping'].includes(camera.status)}
              onClick={() => act('/cameras/' + camera.id + '/' + (['live','reconnecting','obscured'].includes(camera.status) ? 'stop' : 'start'), 'POST')}>
              {camera.status === 'complete' ? 'Replay' : ['live','reconnecting','obscured'].includes(camera.status) ? 'Stop' : 'Start'}
            </Button>}
            {camera?.image && <button className="icon-button" aria-label="Expand camera" onClick={() => { if (document.fullscreenElement) document.exitFullscreen(); else screen.current.requestFullscreen?.().catch(() => {}) }}><Icon name="expand" size={17}/></button>}
            {manager && <button className="icon-button" aria-label="Camera settings" onClick={() => navigate('Cameras')}><Icon name="settings" size={17}/></button>}
          </div></div>
          <CameraFeed camera={camera}/>
          {camera && <div className="feed-meta"><span>{camera.message}</span><span>{camera.status === 'live' ? 'Fresh frame ' + Math.max(0, state.now-camera.frame_at).toFixed(1) + 's ago · ' + camera.frames + ' processed' : camera.status === 'complete' ? 'Recorded sample finished' : ''}</span></div>}
          <DetectedTables camera={camera} onMap={manager ? mapTable : undefined}/>
        </section>
        <section className="panel list-panel" aria-label="Table list">
            {state.tables.length ? <div className="scroll"><table><thead><tr><th>Table</th><th>Capacity</th><th>State / surface</th><th>Time</th><th>Actions</th></tr></thead><tbody>
            {state.tables.map(t => <tr key={t.id}><td><strong>{t.name}</strong></td><td>{t.capacity} seats</td><td><Status state={t.display}/><SurfaceCheck surface={t.surface} now={state.now}/></td>
              <td className="nowrap">{duration(state.now - t.since)}</td><td><TableActions table={t} act={act}/></td></tr>)}
          </tbody></table></div> : <Empty icon="chair">Map a detected table, or draw its seating area in Cameras. Enter the real name and seat count to start occupancy tracking.</Empty>}
          <p className="surface-explainer">Surface checks look for visible cups, bowls, utensils and food. A clear-looking table still needs staff cleaning confirmation.</p>
        </section>
      </div>
      <aside className="panel rail">
        <section><h2>Needs attention</h2>{attention.length ? attention.map(t =>
          <div className="rail-item" key={t.id}><Icon name={t.state === 'waiting' ? 'bell' : 'clean'} size={20}/><div><strong>{t.name} {t.state === 'waiting' ? 'needs service' : 'needs cleaning'}</strong><small>{duration(state.now - t.since)} {t.state === 'waiting' ? 'seated' : 'since departure'}</small></div>
            <Button variant="primary compact" onClick={() => act('/tables/' + t.id + '/' + (t.state === 'waiting' ? 'greet' : 'clean'), 'POST', undefined, 'Table updated.')}>{t.state === 'waiting' ? 'Confirm greeting' : 'Mark cleaned'}</Button>
          </div>) : <Empty icon="check">No tables need attention.</Empty>}</section>
        <section><h2>Waiting parties ({state.queue.length})</h2>{state.queue.length ? state.queue.slice(0, 5).map(p =>
          <div className="rail-item" key={p.id}><Icon name="people"/><div><strong>{p.name}</strong><small>{p.size} guests · {duration(state.now - p.joined)}</small></div>
            <Button variant="primary compact" disabled={!p.suggested.length} onClick={() => chooseParty(p)}>{p.status === 'called' ? 'Seat' : 'Assign'}</Button></div>) : <Empty icon="people">The waitlist is clear.</Empty>}
          {state.queue.length > 5 && <Button onClick={() => navigate('Waitlist')}>View waitlist</Button>}</section>
        <section><h2>Activity</h2>{state.events.length ? <ul className="activity">{state.events.slice(0, 6).map(e =>
          <li key={e.id}><strong>{e.table_name ? e.table_name + ' · ' : ''}{eventLabels[e.kind] || e.kind}</strong><small>{stamp(e.at)}</small></li>)}</ul> : <Empty>Updates appear here as the shift begins.</Empty>}</section>
      </aside>
    </div>
  </>
}
