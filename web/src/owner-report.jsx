import { apiURL } from './paths.mjs'
import React, { useEffect, useState } from 'react'
import { Button, Empty, duration, stamp } from './ui'

function period(range) {
  const now=new Date(), start=new Date(now), end=new Date(now)
  start.setHours(0,0,0,0)
  if(range==='yesterday'){start.setDate(start.getDate()-1);end.setHours(0,0,0,0)}
  if(range==='week')start.setDate(start.getDate()-6)
  if(range==='month')start.setDate(start.getDate()-29)
  if(range==='thisweek'||range==='lastweek'){
    start.setDate(start.getDate()-(start.getDay()+6)%7)
    if(range==='lastweek'){end.setTime(start.getTime());start.setDate(start.getDate()-7)}
  }
  if(range==='weekend'){
    start.setDate(start.getDate()-(start.getDay()+1)%7)
    const monday=new Date(start);monday.setDate(monday.getDate()+2)
    end.setTime(Math.min(now.getTime(),monday.getTime()))
  }
  return {start:start.getTime()/1000,end:end.getTime()/1000,tz:-now.getTimezoneOffset()}
}

const dayName=date=>new Date(date+'T12:00:00').toLocaleDateString([],{weekday:'short',month:'short',day:'numeric'})

export function Analytics({hasEntrance}) {
  const [range,setRange]=useState('week')
  const [report,setReport]=useState(null)
  const [error,setError]=useState('')
  const [revision,refresh]=useState(0)
  const [updated,setUpdated]=useState(null)
  useEffect(()=>{
    let active=true,controller,updating=false
    setReport(null);setUpdated(null);setError('')
    async function update(){
      if(updating)return
      updating=true;controller=new AbortController()
      const timeout=setTimeout(()=>controller.abort(),18000)
      try{
        const {start,end,tz}=period(range)
        const response=await fetch(apiURL(`/analytics?start=${start}&end=${end}&tz=${tz}&period=${range}`),{signal:controller.signal})
        const data=await response.json()
        if(!response.ok)throw new Error(data.detail||'The owner report could not be loaded.')
        if(active){setReport(data);setUpdated(data.synced_at?new Date(data.synced_at):new Date());setError('')}
      }catch(error){if(active)setError(error.name==='AbortError'?'The report connection timed out. Retrying…':error.message)}
      finally{clearTimeout(timeout);updating=false}
    }
    function visible(){if(!document.hidden)update()}
    update();const timer=setInterval(visible,5000)
    document.addEventListener('visibilitychange',visible)
    return()=>{active=false;controller?.abort();clearInterval(timer);document.removeEventListener('visibilitychange',visible)}
  },[range,revision])
  function exportReport(){
    const cell=value=>{
      const string=String(value??'')
      return '"'+(/^[=+@\-\t\r]/.test(string)?"'"+string:string).replaceAll('"','""')+'"'
    }
    const rows=[['Range start',stamp(report.start)],['Range end',stamp(report.end)],['Timezone offset minutes',report.timezone_offset],
      ['Table visits',report.seatings],['Known seated guests',report.guests],['Completed cleanings',report.cleaned],
      ['Footfall crossings',hasEntrance?report.footfall:''],['Occupancy %',report.occupancy],['Turnover',report.turnover],
      ['Average dining seconds',report.dining],['Average wait seconds',report.wait],['Average greeting seconds',report.response],['Average cleaning seconds',report.cleaning],[],
      ['Date','Table visits','Known guests','Unknown party sizes','Occupancy %','Occupied seconds','Turnover','Confirmed cleanings'],
      ...report.daily.map(d=>[d.date,d.seatings,d.guests,d.unknown_party_size,d.occupancy,d.occupied_seconds,d.turnover,d.cleaned]),[],
      ['Table','Occupied seconds','Occupancy %','Turnover'],...report.tables.map(t=>[t.name,t.seconds,t.occupancy,t.turnover])]
    const url=URL.createObjectURL(new Blob([rows.map(row=>row.map(cell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}))
    const link=document.createElement('a');link.href=url;link.download='smartseat-owner-'+range+'.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  const stats=report&&[
    ['Table visits',report.seatings],['Known seated guests',report.guests],['Occupancy',report.occupancy+'%'],['Confirmed cleanings',report.cleaned],
    ['Footfall crossings',hasEntrance?report.footfall:'—'],['Avg. dining',duration(report.dining)],['Avg. greeting',duration(report.response)],['Avg. cleaning',duration(report.cleaning)],
  ]
  const peak=report?.daily.reduce((best,day)=>day.seatings>(best?.seatings||0)?day:best,null)
  const maxVisits=Math.max(1,...(report?.daily.map(day=>day.seatings)||[]))
  return <div className="stack owner-report">
    <div className="report-intro"><p>Your restaurant, day by day. Visits, table use and confirmed service actions from your workspace.</p>
      <div className="actions"><label className="inline-label">Report period <select value={range} onChange={e=>setRange(e.target.value)}>
        <option value="today">Today</option><option value="yesterday">Yesterday</option><option value="week">Last 7 days</option><option value="thisweek">This week</option><option value="lastweek">Last week</option><option value="weekend">Latest weekend</option><option value="month">Last 30 days</option>
      </select></label><Button icon="replay" onClick={()=>refresh(value=>value+1)}>Refresh</Button><Button variant="primary" disabled={!report} onClick={exportReport}>Export CSV</Button></div></div>
    {updated&&<small role="status">{report?.cached?'Saved report · ':'Updated '}{updated.toLocaleString()}{report?.cached?' · restaurant computer disconnected':' · refreshes every 5 seconds'}</small>}
    {error&&<p className="error" role="alert">{error}</p>}
    {!report&&!error&&<p className="muted">Preparing your owner report…</p>}
    {report&&<>
      <div className="metrics report-metrics">{stats.map(([label,value])=><div className="metric" key={label}><div><span>{label}</span><strong>{value}</strong></div></div>)}</div>
      <section className="panel"><div className="panel-head"><h2>Daily table visits</h2><small>{peak?'Busiest day · '+dayName(peak.date):'No recorded visits in this period'}</small></div>
        <div className="daily-chart" role="img" aria-label={'Daily visits: '+report.daily.map(day=>`${day.date}: ${day.seatings}`).join(', ')}>
          {report.daily.map(day=><div className="day-column" key={day.date}><strong>{day.seatings}</strong><div className="day-track"><div className="day-fill" style={{height:day.seatings/maxVisits*100+'%'}}/></div><small>{new Date(day.date+'T12:00:00').toLocaleDateString([],{weekday:'short'})}</small><small>{new Date(day.date+'T12:00:00').toLocaleDateString([],{month:'short',day:'numeric'})}</small></div>)}
        </div>
      </section>
      <section className="panel"><div className="panel-head"><h2>Day-to-day breakdown</h2><small>{stamp(report.start)} – {stamp(report.end)}</small></div>
        <div className="scroll"><table><thead><tr><th>Day</th><th>Visits</th><th>Known guests</th><th>Occupancy</th><th>Turnover</th><th>Cleanings confirmed</th></tr></thead><tbody>
          {report.daily.map(day=><tr key={day.date}><td className="nowrap"><strong>{dayName(day.date)}</strong></td><td>{day.seatings}</td><td>{day.guests}{day.unknown_party_size>0&&<small> · {day.unknown_party_size} parties with unrecorded size</small>}</td><td>{day.occupancy}%</td><td>{day.turnover}</td><td>{day.cleaned}</td></tr>)}
        </tbody></table></div>
        <p className="surface-explainer">Guest totals use recorded party sizes. Camera IDs do not identify unique guests. Cleaning totals count staff confirmations. Occupancy uses elapsed time for mapped tables; no sales or revenue is inferred.</p>
      </section>
      <section className="panel"><div className="panel-head"><h2>Service rhythm</h2><small>Avg. queue wait · {duration(report.wait)}</small></div>
        {report.hourly.length?<div className="bars">{report.hourly.map(hour=><div key={hour.hour}><span>{stamp(hour.hour)}</span><progress max={Math.max(...report.hourly.map(h=>h.visits))} value={hour.visits} aria-label={stamp(hour.hour)+' seatings'}/><strong>{hour.visits}</strong></div>)}</div>:<Empty icon="analytics">Visits will appear here as guests are seated.</Empty>}
      </section>
      <section className="panel"><div className="panel-head"><h2>Per-table performance</h2></div><div className="scroll"><table><thead><tr><th>Table</th><th>Occupied time</th><th>Occupancy</th><th>Turnover</th></tr></thead><tbody>
        {report.tables.map(table=><tr key={table.id}><td><strong>{table.name}</strong></td><td>{duration(table.seconds)}</td><td>{table.occupancy}%</td><td>{table.turnover}</td></tr>)}
      </tbody></table></div>{!report.tables.length&&<Empty>Map your restaurant tables to start collecting occupancy data.</Empty>}</section>
    </>}
  </div>
}
