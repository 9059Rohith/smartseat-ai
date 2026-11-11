import { apiURL } from './paths.mjs'
import React, {useEffect,useState} from 'react'
import {Button} from './ui'

const issues={gateway_offline:'Public application gateway is offline',engine_offline:'Restaurant engine is offline',router_offline:'Local connector router is offline',public_offline:'Public connector is unavailable',camera_blocked:'Camera view is blocked or too dark',camera_unavailable:'Camera capture is unavailable or stopped',capture_unknown:'Camera health is not yet verified',database_missing:'Restaurant database is missing',database_unrecognized:'Restaurant database could not be verified; automatic recovery is paused',unexpected_service:'A configured port belongs to another application'}
const date=value=>value?new Date(value).toLocaleString():'Not verified yet'

export function OperationsStatus(){
  const [data,setData]=useState(null),[error,setError]=useState(''),[revision,refresh]=useState(0)
  useEffect(()=>{
    let active=true,busy=false,controller
    async function update(){
      if(busy)return;busy=true;controller=new AbortController();const timer=setTimeout(()=>controller.abort(),20000)
      try{const response=await fetch(apiURL('/operations'),{signal:controller.signal,cache:'no-store'});const value=await response.json();if(!response.ok)throw new Error(value.detail||'Operational status could not load.');if(active){setData(value);setError('')}}
      catch(e){if(active)setError(e.name==='AbortError'?'The restaurant connection timed out. Retrying…':e.message)}
      finally{clearTimeout(timer);busy=false}
    }
    update();const interval=setInterval(update,30000)
    return()=>{active=false;controller?.abort();clearInterval(interval)}
  },[revision])
  const monitor=data?.monitor,backup=data?.backup
  const stale=monitor?.at&&Date.now()-Date.parse(monitor.at)>180000
  return <section className="panel operations-status"><div className="panel-head"><h2>Restaurant safeguards</h2><Button disabled={!data&&!error} onClick={()=>refresh(value=>value+1)}>Refresh status</Button></div>
    {error&&<p className="error" role="alert">{error}</p>}{!data&&!error&&<p>Checking the restaurant computer…</p>}
    {data&&<>
      <div className="two"><div><h3>Monitoring & recovery</h3><p><strong>{!monitor?'Monitor not installed or not checked yet':stale?'Monitor update is overdue':monitor.state==='healthy'?'Services healthy':monitor.state==='critical'?'Service recovery needs attention':'Attention required'}</strong></p><small>Last check · {date(monitor?.at)}</small>
        {!!monitor?.issues?.length&&<ul>{monitor.issues.map(issue=><li key={issue}>{issues[issue]||'An operational check needs attention'}</li>)}</ul>}
        <p>Last recovery · {date(monitor?.last_recovery_at)}{monitor?.recovery_ok===false?' · unsuccessful':''}</p></div>
      <div><h3>Encrypted backups</h3><p><strong>{backup?.ok?'Last backup succeeded':backup?'Last backup needs attention':'No verified backup status yet'}</strong></p><small>Last backup · {date(backup?.at)}</small><p>Restore verified · {date(backup?.last_restore_verified_at)}</p><p>Cloud snapshot · {backup?.cloud_state||'Not verified yet'}</p></div></div>
      <h3>Data retention preview</h3><p>{data.retention.review} No automatic deletion is enabled.</p><p>{data.retention.camera_recording}</p>
      <div className="scroll"><table><thead><tr><th>Record type</th><th>Proposed age</th><th>Records eligible for review</th></tr></thead><tbody>{Object.entries(data.retention.candidates).map(([kind,count])=><tr key={kind}><td>{kind.replaceAll('_',' ')}</td><td>{data.retention.proposed_days[kind]?data.retention.proposed_days[kind]+' days':'Already expired'}</td><td>{count}</td></tr>)}</tbody></table></div>
      <h3>Restaurant access</h3><p>{data.mapped_tables} real camera zones mapped. A visible tabletop and seating area are needed to calibrate occupancy.</p><ul>{data.staff.map(member=><li key={member.name}>{member.name} · {member.role}</li>)}</ul><small>Managers manage cameras, staff accounts and safeguards. Restaurant credentials remain separate from Google sign-in. Keep the restaurant computer awake and online for live detection.</small>
    </>}
  </section>
}
