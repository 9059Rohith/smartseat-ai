import React, { useState } from 'react'
import { CameraFeed, DetectedTables } from './floor'
import { Button, Empty, Icon, Modal, cameraLabels, field } from './ui'

export function CameraForm({ close, act, select }) {
  const [kind, setKind] = useState('webcam')
  return <Modal title="Add camera" close={close}><form onSubmit={async e => {
    e.preventDefault()
    const form = e.currentTarget
    const result = await act('/cameras', 'POST', { name: field(form, 'name'), kind, source: field(form, 'source') }, 'Camera added.')
    if (result) { select(result.id); close() }
  }}><label>Camera name<input name="name" required maxLength="80" autoFocus/></label>
    <label>Source<select value={kind} onChange={e => setKind(e.target.value)}><option value="webcam">Laptop or USB webcam</option><option value="rtsp">RTSP network camera</option></select></label>
    {kind === 'webcam' ? <label>Webcam index<input key="webcam" name="source" type="number" min="0" max="16" defaultValue="0" required/></label> :
      <label>RTSP URL<input key="rtsp" name="source" type="password" placeholder="rtsp://camera-address/stream" maxLength="1024" required autoComplete="off"/></label>}
    <div className="form-actions"><Button type="button" onClick={close}>Cancel</Button><Button type="submit" variant="primary">Save camera</Button></div>
  </form></Modal>
}

export function StaffForm({ close, act }) {
  return <Modal title="Create staff account" close={close}><form onSubmit={async e => {
    e.preventDefault()
    const form = e.currentTarget
    if (await act('/users', 'POST', { name: field(form, 'name'), password: field(form, 'password'), role: field(form, 'role') }, 'Account created.')) close()
  }}><label>Username<input name="name" required maxLength="80" autoFocus autoComplete="off"/></label>
    <label>Password (12 characters or more)<input name="password" type="password" minLength="12" maxLength="160" required autoComplete="new-password"/></label>
    <label>Role<select name="role"><option value="staff">Staff</option><option value="manager">Manager</option></select></label>
    <div className="form-actions"><Button type="button" onClick={close}>Cancel</Button><Button type="submit" variant="primary">Create account</Button></div>
  </form></Modal>
}

function Draw({ camera, points, setPoints }) {
  const [fixedFrame, setFixedFrame] = useState(null)
  function add(x, y) {
    if (points.length < 32) setPoints(prev => [...prev, [Number(x.toFixed(4)), Number(y.toFixed(4))]])
  }
  return <>
    <CameraFeed camera={camera} raw fixedFrame={fixedFrame}>
      <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" className="drawing" role="img" aria-label="Click to add corners to the camera zone"
        onClick={e => {
          const r = e.currentTarget.getBoundingClientRect()
          setFixedFrame(camera.frame_at)
          add((e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height)
        }}>
        <polygon points={points.map(([x,y]) => x*1000 + ',' + y*1000).join(' ')}/>
        {points.map(([x,y], i) => <circle key={i} cx={x*1000} cy={y*1000} r="8"/>)}
      </svg>
    </CameraFeed>
    <div className="actions"><span className="muted">{points.length} corners · Draw around the table and its chairs</span>
      <Button type="button" variant="compact" disabled={!points.length} onClick={() => setPoints(prev => prev.slice(0,-1))}>Undo</Button>
      <Button type="button" variant="compact" disabled={!points.length} onClick={() => { setPoints([]); setFixedFrame(null) }}>Clear</Button>
    </div>
    <details className="coordinates"><summary>Enter a corner by coordinates</summary><div className="two">
      <label>X (0–1)<input type="number" id="point-x" min="0" max="1" step=".001" defaultValue="0"/></label>
      <label>Y (0–1)<input type="number" id="point-y" min="0" max="1" step=".001" defaultValue="0"/></label>
    </div><Button type="button" onClick={() => {
      const x = document.getElementById('point-x').valueAsNumber, y = document.getElementById('point-y').valueAsNumber
      if (x >= 0 && x <= 1 && y >= 0 && y <= 1) add(x, y)
    }}>Add corner</Button></details>
  </>
}

export function TableForm({ close, act, cameras, table, selected, suggestion }) {
  const [cameraId, choose] = useState(table ? table.camera || '' : suggestion?.camera || selected || '')
  const [points, setPoints] = useState(table?.zone || suggestion?.zone || [])
  const camera = cameras.find(c => c.id === Number(cameraId))
  return <Modal title={table ? 'Edit ' + table.name : 'Add table'} close={close}><form onSubmit={async e => {
    e.preventDefault()
    const form = e.currentTarget
    const data = { name: field(form, 'name'), capacity: Number(field(form, 'capacity')), camera: cameraId ? Number(cameraId) : null, zone: points, vision: Boolean(field(form, 'vision')) }
    if (await act('/tables' + (table ? '/' + table.id : ''), table ? 'PUT' : 'POST', data, 'Table saved.')) close()
  }}>
    <div className="two"><label>Table name<input name="name" defaultValue={table?.name || ''} maxLength="80" required autoFocus/></label>
      <label>Seats<input name="capacity" type="number" min="1" max="60" defaultValue={table?.capacity || ''} required/></label></div>
    <label>Camera<select aria-label="Table camera" value={cameraId} onChange={e => { choose(e.target.value); setPoints([]) }}><option value="">Manual updates only</option>{cameras.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
    {camera && <Draw key={camera.id} camera={camera} points={points} setPoints={setPoints}/>}
    {camera && <label className="checkbox"><input type="checkbox" name="vision" defaultChecked={table ? Boolean(table.vision) : true}/>Automatically update occupancy</label>}
    <div className="form-actions"><Button type="button" onClick={close}>Cancel</Button><Button type="submit" variant="primary" disabled={Boolean(camera) && points.length < 3}>Save table</Button></div>
  </form></Modal>
}

export function EntranceForm({ camera, act, close }) {
  const [points, setPoints] = useState(camera.entrance)
  return <Modal title="Entrance zone" close={close}><form onSubmit={async e => {
    e.preventDefault()
    if (await act('/cameras/' + camera.id + '/entrance', 'PUT', { zone: points }, 'Entrance zone saved.')) close()
  }}>
    <p className="muted">Draw the inward side of the entrance. The camera must also see the area just outside your outline.</p>
    <Draw camera={camera} points={points} setPoints={setPoints}/>
    <div className="form-actions"><Button type="button" onClick={close}>Cancel</Button><Button type="submit" variant="primary" disabled={points.length > 0 && points.length < 3}>Save entrance</Button></div>
  </form></Modal>
}

export function Setup({ state, camera, setCamera, act, open, manager }) {
  const active = camera && ['live','reconnecting','starting','stopping','obscured'].includes(camera.status)
  return <div className="stack">
    <section className="panel camera-panel">
      <div className="panel-head"><h2>Camera sources</h2>{manager && <Button variant="primary" icon="plus" onClick={() => open('camera')}>Add camera</Button>}</div>
      {state.cameras.length ? <>
        <div className="sources">{state.cameras.map(c => <button key={c.id} className={'source ' + (camera?.id === c.id ? 'selected' : '')} onClick={() => setCamera(c.id)}><Icon name="camera"/><span><strong>{c.name}</strong><small>{cameraLabels[c.status]}</small></span></button>)}</div>
        <CameraFeed camera={camera}/>
        {camera && <div className="feed-meta"><span>{camera.message}</span><div className="actions">{manager && <>
          <Button disabled={['starting','stopping'].includes(camera.status)} onClick={() => act('/cameras/' + camera.id + '/' + (active ? 'stop' : 'start'), 'POST')}>{active ? 'Stop camera' : camera.status === 'complete' ? 'Replay sample' : 'Start camera'}</Button>
          <Button disabled={!camera.image} onClick={() => open('entrance')}>Map entrance</Button>
        </>}</div></div>}
        <DetectedTables camera={camera} onMap={manager ? item => open('table', undefined, { camera: camera.id, zone: item.zone }) : undefined}/>
      </> : <Empty icon="camera">Add a laptop camera or an RTSP camera to begin.</Empty>}
    </section>
    <section className="panel"><div className="panel-head"><h2>Table zones</h2>{manager && <Button icon="plus" onClick={() => open('table')}>Add table</Button>}</div>
      {state.tables.length ? <div className="scroll"><table><thead><tr><th>Table</th><th>Seats</th><th>Camera</th><th>Occupancy</th>{manager && <th>Actions</th>}</tr></thead>
        <tbody>{state.tables.map(t => <tr key={t.id}><td><strong>{t.name}</strong></td><td>{t.capacity}</td><td>{state.cameras.find(c => c.id === t.camera)?.name || '—'}</td>
          <td>{t.camera && t.vision ? 'Automatic' : 'Manual'}</td>{manager && <td><Button variant="compact" onClick={() => open('table', t.id)}>Edit zone</Button></td>}</tr>)}</tbody></table></div> :
        <Empty icon="chair">Add a table to define its capacity and camera zone.</Empty>}</section>
    {manager && <section className="panel"><div className="panel-head"><h2>Staff access</h2><Button onClick={() => open('staff')}>Create account</Button></div></section>}
  </div>
}
