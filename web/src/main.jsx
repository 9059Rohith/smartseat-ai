import React, { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Button, Icon, NoticeContext, cameraLabels, field, request } from './ui'
import { Floor } from './floor'
import { Analytics, PartyForm, ReservationForm, Reservations, SeatForm, Waitlist } from './operations'
import { CameraForm, EntranceForm, Setup, StaffForm, TableForm } from './setup'
import './style.css'
import './cinematic.css'
import { AnimatedTitle, Atmosphere, MotionControls, useAtmosphere } from './atmosphere'
import { Account, CloudLogin } from './account'
import { MediaAnalysis } from './media-analysis'

const nav = [['Floor','floor'], ['Waitlist','people'], ['Reservations','calendar'], ['Analytics','analytics'], ['Cameras','camera'], ['Media Analysis','media']]

function Login({ demo, onLogin, engineError }) {
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  return <main className="sign-in"><div className="login panel">
    <div className="login-brand"><Icon name="chair" size={40}/><h1>SmartSeat AI</h1></div>
    <p className="muted">{demo ? 'Sample workspace · demo / smartseat-demo' : 'Sign in to your restaurant workspace.'}</p>
    {engineError && <p className="error" role="status">Restaurant engine is unavailable. Keep the restaurant computer and its public connection running.</p>}
    <form onSubmit={async e => {
      e.preventDefault()
      const form = e.currentTarget
      setPending(true); setError('')
      try { onLogin(await request('/login', 'POST', { name: field(form, 'name'), password: field(form, 'password') })) }
      catch (e) { setError(e.message) }
      finally { setPending(false) }
    }}>
      <label>Username<input name="name" autoComplete="username" defaultValue={demo ? 'demo' : ''} required autoFocus/></label>
      <label>Password<input name="password" autoComplete="current-password" type="password" defaultValue={demo ? 'smartseat-demo' : ''} required/></label>
      {error && <p className="error" role="alert">{error}</p>}
      <Button variant="primary" type="submit" disabled={pending}>{pending ? 'Signing in…' : 'Sign in'}</Button>
    </form>
  </div></main>
}

function App() {
  const [user, setUser] = useState(undefined)
  const [authConfig, setAuthConfig] = useState(null)
  const [recovery, setRecovery] = useState(new URLSearchParams(location.search).get('reset_password')==='1')
  const [demo, setDemo] = useState(false)
  const [state, setState] = useState(null)
  const [tab, navigate] = useState('Floor')
  const [cameraId, setCamera] = useState(null)
  const [modal, setModal] = useState(null)
  const [notice, setNotice] = useState(null)
  const [connection, setConnection] = useState(false)
  const [loadingError, setLoadingError] = useState('')
  const running = useRef(new Set())
  const atmosphere = useAtmosphere(tab, Boolean(state))
  const close = () => setModal(null)
  const open = (kind, id, suggestion) => { setNotice(null); setModal({ kind, id, suggestion }) }
  useEffect(() => {
    if(!['127.0.0.1','localhost'].includes(location.hostname))request('/auth/config').then(setAuthConfig).catch(()=>setAuthConfig({enabled:false}))
    request('/health').then(data => setDemo(data.demo)).catch(e => setLoadingError(e.message))
    request('/me').then(setUser).catch(() => setUser(null))
  }, [])
  useEffect(() => {
    if (!user) { setState(null); return }
    if(!['127.0.0.1','localhost'].includes(location.hostname)){
      let active=true,timer,controller
      async function poll(){
        controller=new AbortController()
        const timeout=setTimeout(()=>controller.abort(),20000)
        try{
          const response=await fetch('/api/state',{signal:controller.signal,cache:'no-store'})
          if(response.status===401){if(active)setUser(null);return}
          if(!response.ok)throw new Error('Restaurant engine is unavailable.')
          const data=await response.json()
          if(active){setState(data);setConnection(data.engine_connected!==false);setLoadingError('')}
          if(active&&user.cloud&&data.engine_connected&&!user.engine_access){
            request('/me').then(session=>{if(active&&session?.engine_access)setUser(session)}).catch(()=>{})
          }
        }catch(error){if(active){setConnection(false);setLoadingError('Restaurant engine is unavailable.');if(user.cloud)setState(previous=>previous?{...previous,engine_connected:false,cameras:previous.cameras.map(camera=>({...camera,status:'reconnecting',image:false,detected_tables:[],people:0,chairs:0})),tables:previous.tables.map(table=>({...table,display:'unknown',observed:false,surface:{state:'unknown',at:null,items:[]}}))}:previous)}}
        finally{clearTimeout(timeout);if(active)timer=setTimeout(poll,2000)}
      }
      poll()
      return()=>{active=false;controller?.abort();clearTimeout(timer)}
    }
    const live = new EventSource('/api/live')
    live.onmessage = event => { setState(JSON.parse(event.data)); setConnection(true) }
    live.onerror = () => { setConnection(false); request('/me').then(session => { if (!session) setUser(null) }).catch(() => {}) }
    request('/state').then(setState).catch(e => setLoadingError(e.message))
    return () => live.close()
  }, [user])
  useEffect(() => {
    if (!notice || notice.error) return
    const timer = setTimeout(() => setNotice(null), 5000)
    return () => clearTimeout(timer)
  }, [notice])
  async function act(path, method, body, success) {
    if(user?.cloud && !connection && path!=='/logout'){setNotice({message:'Connect your restaurant computer from Account before changing the floor.',error:true});return null}
    const action = method + ' ' + path
    if (running.current.has(action)) return null
    running.current.add(action)
    try {
      const result = await request(path, method, body)
      setNotice(success ? { message: success } : null)
      if (path === '/logout') { setUser(null); navigate('Floor'); close() }
      else request('/state').then(setState).catch(() => {})
      return result
    } catch (e) {
      if (e.status === 401 && !user?.cloud) setUser(null)
      setNotice({ message: e.message, error: true })
      return null
    } finally {
      running.current.delete(action)
    }
  }
  if (user === undefined || (!['127.0.0.1','localhost'].includes(location.hostname)&&authConfig===null)) return <main className="loading">Opening SmartSeat…</main>
  if(recovery&&user?.cloud)return <><Atmosphere scene={atmosphere.scene}/><CloudLogin config={authConfig||{}} recovery onRecovered={()=>setRecovery(false)}/></>
  if(user===null&&authConfig?.enabled)return <><Atmosphere scene={atmosphere.scene}/><CloudLogin config={authConfig} onLogin={setUser}/></>
  if (user === null) return <><Atmosphere scene={atmosphere.scene}/><Login demo={demo} engineError={loadingError} onLogin={value=>{setLoadingError('');setUser(value)}}/></>
  const camera = state?.cameras.find(c => c.id === cameraId) || state?.cameras.find(c => c.kind === 'webcam') || state?.cameras[0]
  const manager = user.role === 'manager'
  const chooseParty = party => open('seat', party.id)
  const party = state?.queue.find(p => p.id === modal?.id)
  const table = state?.tables.find(t => t.id === modal?.id)
  const pageTitle = tab === 'Floor' ? 'Dining room' : tab
  return <NoticeContext.Provider value={notice}><div className="app">
    <Atmosphere scene={atmosphere.scene}/><div className="reading-progress" aria-hidden="true"/>
    <aside className="sidebar">
      <div className="brand"><Icon name="chair" size={39}/><span>SmartSeat<span className="brand-dot">.</span></span></div>
      <nav aria-label="Main navigation">{[...nav,...(user.cloud?[['Account','people']]:[])].map(([name, icon]) =>
        <button key={name} aria-label={name} title={name} className={tab === name ? 'active' : ''} aria-current={tab === name ? 'page' : undefined} onClick={() => navigate(name)}><Icon name={icon}/><span>{name}</span></button>)}</nav>
      <div className="side-bottom"><div><Icon name="screen" size={18}/><i className="dot"/><span>On-device processing</span></div>
        <button className="signout" aria-label="Sign out" onClick={() => act('/logout', 'POST')}><Icon name="logout" size={18}/><span>Sign out · {user.name}</span></button></div>
    </aside>
    <main className="workspace">
      <header className="workspace-head"><div><AnimatedTitle key={tab}>{pageTitle}</AnimatedTitle>
        <p className="subtitle"><i className={'dot ' + (camera?.status === 'live' ? '' : 'neutral')}/>{tab==='Media Analysis'?'Uploaded images & videos · local inference':camera ? camera.name + ' · ' + cameraLabels[camera.status] : 'Restaurant workspace'}{demo && <span className="demo-label">Sample workspace</span>}</p></div>
        <div className="header-actions"><MotionControls {...atmosphere}/>{!['Account','Media Analysis'].includes(tab)&&(tab === 'Reservations' ? <Button disabled={user.cloud&&!connection} variant="primary" icon="plus" onClick={() => open('reservation')}>New reservation</Button> : <Button disabled={user.cloud&&!connection} variant="primary" icon="plus" onClick={() => open('party')}>Add party</Button>)}</div></header>
      {!connection && state && <div className="connection" role="status">{user.cloud?'Restaurant computer is disconnected. '+(state.cloud_saved_at?'Showing saved records from '+new Date(state.cloud_saved_at).toLocaleString()+'.':'Connect your restaurant to start collecting real data.'):'Reconnecting to SmartSeat. The floor shows the last update.'}{user.cloud&&<Button onClick={()=>navigate('Account')}>Open Account</Button>}</div>}
      {user.cloud&&tab==='Account'&&<Account user={user} onUser={setUser}/>}
      {tab==='Media Analysis'&&<MediaAnalysis available={!user.cloud||connection} onAccount={()=>navigate('Account')}/>}
      {!state && <p className="muted">{loadingError || 'Connecting to the restaurant workspace…'}</p>}
      {state && tab === 'Floor' && <Floor state={state} camera={camera} setCamera={setCamera} act={act} manager={manager} navigate={navigate} chooseParty={chooseParty} mapTable={item => open('table', undefined, { camera: camera.id, zone: item.zone })}/>}
      {state && tab === 'Waitlist' && <Waitlist state={state} act={act} chooseParty={chooseParty}/>}
      {state && tab === 'Reservations' && <Reservations state={state} act={act}/>}
      {state && tab === 'Analytics' && <Analytics hasEntrance={state.cameras.some(c => c.entrance.length > 0)}/>}
      {state && tab === 'Cameras' && <Setup state={state} camera={camera} setCamera={setCamera} act={act} open={open} manager={manager}/>}
    </main>
    {notice && !modal && <div className={'toast ' + (notice.error ? 'error' : '')} role={notice.error ? 'alert' : 'status'}>{notice.message}<button className="icon-button" aria-label="Dismiss message" onClick={() => setNotice(null)}><Icon name="close" size={16}/></button></div>}
    {state && modal?.kind === 'party' && <PartyForm close={close} act={act}/>}
    {state && modal?.kind === 'seat' && party && <SeatForm close={close} act={act} party={party} tables={state.tables}/>}
    {state && modal?.kind === 'reservation' && <ReservationForm close={close} act={act} tables={state.tables}/>}
    {state && modal?.kind === 'camera' && <CameraForm close={close} act={act} select={setCamera}/>}
    {state && modal?.kind === 'table' && <TableForm close={close} act={act} cameras={state.cameras} table={table} selected={camera?.id} suggestion={modal.suggestion}/>}
    {state && modal?.kind === 'entrance' && camera && <EntranceForm camera={camera} close={close} act={act}/>}
    {state && modal?.kind === 'staff' && <StaffForm close={close} act={act}/>}
  </div></NoticeContext.Provider>
}

createRoot(document.getElementById('root')).render(<App/>)


import './account.css'
