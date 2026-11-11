import { apiURL } from './paths.mjs'
import React, { useEffect, useRef, useState } from 'react'
import { Button, Icon } from './ui'
import { mediaCSV, mediaStates, mediaTime, sampleTimes, saveBlob, waitForMedia } from './media-helpers.mjs'
import './media-analysis.css'

const empty={tables:0,people:0,chairs:0,occupied:0,items_present:0,looks_clear:0,unknown:0}

async function mediaRequest(path,method,body,signal) {
  const response=await fetch(apiURL('/media/'+path),{method,headers:body?{'Content-Type':'application/json'}:{},
    body:body?JSON.stringify(body):undefined,cache:'no-store',signal:AbortSignal.any([signal,AbortSignal.timeout(20000)])})
  const data=await response.json().catch(()=>({detail:'The restaurant engine did not return a valid response.'}))
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'This media request could not be processed.')
  return data
}

function delay(ms,signal) {
  return new Promise((resolve,reject)=>{
    const abort=()=>{clearTimeout(timer);reject(new DOMException('Stopped','AbortError'))}
    const timer=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve()},ms)
    if(signal.aborted)abort();else signal.addEventListener('abort',abort,{once:true})
  })
}

function frameJPEG(element,width,height) {
  if(!width||!height||width*height>80000000)throw new Error('Choose a smaller image or video resolution.')
  const scale=Math.min(1,960/Math.max(width,height)),canvas=document.createElement('canvas')
  canvas.width=Math.max(16,Math.round(width*scale));canvas.height=Math.max(16,Math.round(height*scale))
  canvas.getContext('2d').drawImage(element,0,0,canvas.width,canvas.height)
  const jpeg=canvas.toDataURL('image/jpeg',.8)
  if(jpeg.length>950000)throw new Error('This frame is too detailed to send. Try a smaller image or video resolution.')
  return jpeg
}

function FrameView({frame}) {
  return <div className="media-frame" style={{aspectRatio:frame.width+'/'+frame.height}}>
    <img src={frame.preview} alt={'Uploaded media at '+mediaTime(frame.frame_time)}/>
    <svg viewBox={'0 0 '+frame.width+' '+frame.height} role="img" aria-label={frame.tables.length+' colored table outlines'}>
      {frame.people.map((person,index)=><rect key={'p'+index} x={person.box[0]} y={person.box[1]} width={person.box[2]-person.box[0]} height={person.box[3]-person.box[1]} fill="none" stroke="#7dd3fc" strokeWidth="2" strokeDasharray="6 5"/>)}
      {frame.tables.map(table=>{
        const x=Math.max(0,Math.min(table.box[0],frame.width-190)),y=Math.max(22,table.box[1])
        return <g key={table.id}>
          <polygon points={table.zone.map(([a,b])=>[a*frame.width,b*frame.height].join(',')).join(' ')} fill={table.color} fillOpacity=".16" stroke={table.color} strokeWidth="3"/>
          <rect x={x} y={y-22} width="190" height="23" rx="4" fill="#10180f" fillOpacity=".95"/>
          <text x={x+6} y={y-6} fill={table.color} fontSize="15" fontFamily="Arial, sans-serif" fontWeight="bold">T{table.id} · {mediaStates[table.state].label}</text>
        </g>
      })}
    </svg>
    {frame.view==='blocked'&&<span className="media-view-warning">Dark or blocked image · surface unverified</span>}
  </div>
}

async function downloadFrame(frame) {
  const image=new Image();image.src=frame.preview;await image.decode()
  const canvas=document.createElement('canvas');canvas.width=frame.width;canvas.height=frame.height
  const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0)
  for(const table of frame.tables){
    ctx.beginPath();table.zone.forEach(([x,y],i)=>i?ctx.lineTo(x*frame.width,y*frame.height):ctx.moveTo(x*frame.width,y*frame.height));ctx.closePath()
    ctx.fillStyle=table.color;ctx.globalAlpha=.16;ctx.fill();ctx.globalAlpha=1;ctx.strokeStyle=table.color;ctx.lineWidth=3;ctx.stroke()
    const x=Math.max(0,Math.min(table.box[0],frame.width-220)),y=Math.max(24,table.box[1])
    ctx.fillStyle='#10180f';ctx.fillRect(x,y-24,220,24);ctx.fillStyle=table.color;ctx.font='bold 16px Arial'
    ctx.fillText('T'+table.id+' · '+mediaStates[table.state].label,x+5,y-6)
  }
  canvas.toBlob(blob=>{if(blob)saveBlob(blob,'smartseat-frame-'+frame.frame_time.toFixed(2)+'.png')})
}

export function MediaAnalysis({available,onAccount}) {
  const [file,setFile]=useState(null),[url,setURL]=useState(''),[results,setResults]=useState([]),[index,setIndex]=useState(0)
  const [busy,setBusy]=useState(false),[progress,setProgress]=useState(null),[error,setError]=useState('')
  const [broad,setBroad]=useState(true),[playing,setPlaying]=useState(false),[stopped,setStopped]=useState(false)
  const run=useRef(0),controller=useRef(null),job=useRef(null),picker=useRef(null)
  const video=file?.type.startsWith('video/'),frame=results[index],summary=frame?.summary||empty
  useEffect(()=>()=>{if(url)URL.revokeObjectURL(url)},[url])
  useEffect(()=>()=>{run.current++;controller.current?.abort();if(job.current)fetch(apiURL('/media/jobs/'+job.current),{method:'DELETE',signal:AbortSignal.timeout(5000)}).catch(()=>{})},[])
  useEffect(()=>{
    if(!playing||busy||results.length<2)return
    const timer=setInterval(()=>setIndex(previous=>previous+1<results.length?previous+1:0),700)
    return()=>clearInterval(timer)
  },[playing,busy,results.length])

  function stop() {controller.current?.abort();setPlaying(false)}
  function choose(selected) {
    if(!selected)return
    stop();run.current++;setBusy(false);setError('');setResults([]);setIndex(0);setProgress(null);setStopped(false)
    if(!/^(image\/(jpeg|png|webp)|video\/)/.test(selected.type)){setFile(null);setURL('');setError('Choose a JPEG, PNG, WebP or a browser-supported video file.');return}
    if(selected.size>250*1024*1024){setFile(null);setURL('');setError('Choose a file under 250 MB.');return}
    setFile(selected);setURL(URL.createObjectURL(selected));setBroad(!selected.type.startsWith('video/'))
  }
  function clear() {stop();run.current++;setBusy(false);setFile(null);setURL('');setResults([]);setProgress(null);setError('');setStopped(false);if(picker.current)picker.current.value=''}

  async function analyzeMedia() {
    if(!file||busy||!available)return
    const current=++run.current,abort=new AbortController();controller.current=abort
    setBusy(true);setResults([]);setIndex(0);setProgress(null);setError('');setStopped(false);setPlaying(false)
    let element
    try{
      element=document.createElement(video?'video':'img')
      if(video){element.preload='auto';element.muted=true;element.playsInline=true}
      await waitForMedia(element,video?'loadeddata':'load',abort.signal,()=>{element.src=url})
      const times=video?sampleTimes(element.duration):[0]
      for(let i=0;i<times.length;i++){
        if(abort.signal.aborted)throw new DOMException('Stopped','AbortError')
        setProgress({done:i,total:times.length,at:times[i]})
        if(video&&Math.abs(element.currentTime-times[i])>.001)await waitForMedia(element,'seeked',abort.signal,()=>{element.currentTime=times[i]})
        const preview=frameJPEG(element,video?element.videoWidth:element.naturalWidth,video?element.videoHeight:element.naturalHeight)
        const created=await mediaRequest('analyze','POST',{image:preview,broad,frame_time:times[i]},abort.signal)
        job.current=created.id
        let data,deadline=Date.now()+120000
        try{
          while(Date.now()<deadline){
            const status=await mediaRequest('jobs/'+created.id,'GET',undefined,abort.signal)
            if(status.status==='error')throw new Error(status.error)
            if(status.status==='done'){data=status.result;break}
            await delay(450,abort.signal)
          }
          if(!data)throw new Error('This frame took too long. Try the fast scan or check the engine.')
        }finally{
          fetch(apiURL('/media/jobs/'+created.id),{method:'DELETE',signal:AbortSignal.timeout(5000)}).catch(()=>{})
          if(job.current===created.id)job.current=null
        }
        if(run.current!==current)return
        setResults(previous=>[...previous,{...data,preview}]);setIndex(i);setProgress({done:i+1,total:times.length,at:times[i]})
      }
    }catch(failure){
      if(run.current===current){if(failure.name==='AbortError')setStopped(true);else setError(failure.message||'Media analysis failed.')}
    }finally{
      if(video&&element){element.pause();element.removeAttribute('src');element.load()}
      if(run.current===current){setBusy(false);controller.current=null}
    }
  }

  return <div className="media-analysis">
    <p className="media-intro">A closer look, frame by frame. Upload a photo or video to inspect real table proposals, people and visible dining items.</p>
    {!available&&<div className="media-connect" role="status">Connect your restaurant computer to run its local models. <Button onClick={onAccount}>Open Account</Button></div>}
    <section className="panel media-upload" aria-label="Upload media">
      <div className="media-upload-copy"><div className="media-eyebrow">Image & video analysis</div><h2>Bring your own view.</h2><p>Choose a file from this device. Selected frames are analyzed on your paired restaurant computer.</p></div>
      <div className="media-upload-controls">
        <label className="media-picker">Image or video<input ref={picker} type="file" accept="image/jpeg,image/png,image/webp,video/*" onChange={event=>choose(event.target.files?.[0])}/></label>
        <p className="muted">{file?file.name+' · '+(file.size/1024/1024).toFixed(1)+' MB':'JPEG, PNG, WebP, MP4 or WebM · up to 250 MB / 10 minutes'}</p>
        <label className="media-option"><input type="checkbox" checked={broad} disabled={busy} onChange={event=>setBroad(event.target.checked)}/> Broader table & desk scan <span>(slower)</span></label>
        <div className="actions"><Button variant="primary" icon="analytics" disabled={!file||busy||!available} onClick={analyzeMedia}>{busy?'Analyzing…':video?'Analyze video':'Analyze image'}</Button>{busy?<Button onClick={stop}>Stop analysis</Button>:file&&<Button onClick={clear}>Clear upload</Button>}</div>
      </div>
    </section>
    {error&&<p className="error media-message" role="alert">{error}</p>}
    {progress&&<div className="media-progress" role="status"><span>{busy?'Analyzing':stopped?'Stopped · retained completed frames':'Analyzed'} {progress.done} / {progress.total} {video?'sampled frames':'image'}{busy?' · source '+mediaTime(progress.at):''}</span><progress max={progress.total} value={progress.done}/></div>}
    <section className="media-stats" aria-label="Uploaded media statistics">
      {[['tables','Table candidates',null],['occupied','In use','#fb7185'],['items_present','Items remain','#fbbf24'],['looks_clear','Looks clear','#86efac'],['unknown','Unverified','#a8b3bd'],['people','People','#7dd3fc']].map(([key,label,color])=><div key={key} style={{'--stat-color':color||'#dfb682'}}><span>{label}</span><strong>{frame?summary[key]:'—'}</strong></div>)}
    </section>
    <div className="media-legend" aria-label="Detection color legend">{Object.entries(mediaStates).map(([key,value])=><span key={key}><i style={{background:value.color}}/>{value.label}</span>)}<span><i style={{background:'#7dd3fc'}}/>Person outline</span></div>
    <div className="media-results-grid">
      <section className="panel media-review" aria-label="Annotated media review">
        <div className="panel-head"><h2>{video?'Video frame review':'Image review'}</h2>{frame&&<span className="muted">{video?mediaTime(frame.frame_time)+' · ':''}{frame.width} × {frame.height}</span>}</div>
        {frame?<FrameView frame={frame}/>:<div className="media-placeholder"><Icon name="media" size={44}/><strong>{busy?'Running actual local inference…':'Your analysis appears here.'}</strong><span>Choose a file and analyze it. No example detections are inserted.</span></div>}
        {video&&results.length>0&&<div className="media-timeline"><Button disabled={busy||results.length<2} onClick={()=>setPlaying(value=>!value)}>{playing?'Pause review':'Play review'}</Button><input type="range" aria-label="Analyzed frame" min="0" max={Math.max(0,results.length-1)} value={index} disabled={busy||results.length<2} onChange={event=>{setPlaying(false);setIndex(Number(event.target.value))}}/><span>Frame {index+1} / {results.length}</span></div>}
        {frame&&<div className="media-frame-meta"><span>{summary.chairs} chairs · {frame.inference_ms?Math.round(frame.inference_ms)+' ms inference':'No usable visual evidence'}</span><span>{frame.broad_status==='complete'?'YOLOX + broader table scan':frame.broad_status==='unavailable'?'YOLOX · broader model unavailable':'YOLOX local scan'}</span></div>}
        {frame&&<div className="actions media-downloads"><Button onClick={()=>downloadFrame(frame).catch(()=>setError('The annotated frame could not be downloaded.'))}>Download annotated frame</Button><Button onClick={()=>saveBlob(new Blob([mediaCSV(results)],{type:'text/csv;charset=utf-8'}),'smartseat-media-analysis.csv')}>Export frame statistics</Button></div>}
      </section>
      <section className="panel media-details"><div className="panel-head"><h2>In this frame</h2></div>
        {frame?.tables.length>0?<ul>{frame.tables.map(table=><li key={table.id}><div><strong style={{color:table.color}}>T{table.id} · {mediaStates[table.state].label}</strong><span>Model score {Math.round(table.confidence*100)}% · {table.people} overlapping {table.people===1?'person':'people'}</span></div><p>{table.items.length?table.items.map(item=>item.label).join(', '):'No supported dining items detected in this region.'}</p></li>)}</ul>:<p className="muted">{frame?'No table candidates in this frame. Try a clearer view or the broader scan.':'Table details will follow the selected analyzed frame.'}</p>}
        <div className="media-scope"><strong>Visual evidence, with context.</strong><p>In use means visible person overlap, not confirmed seating. Looks clear means no supported items were detected, not that the table is sanitized. Staff still confirm cleaning.</p><p>{video?'Video is sampled across its duration, up to 120 frames. Review playback shows those analyzed snapshots, not continuous tracking. T-numbers and summary counts apply to one frame; they are not unique tables or guests across the clip.':'Each T-number is a proposal in this image. It does not create a table in your restaurant.'}</p><p>Uploads do not change live camera feeds, saved tables, visits or owner reports. Source files stay in your browser; submitted frames are processed in memory, with temporary jobs expiring after five minutes.</p></div>
      </section>
    </div>
    {file&&url&&<details className="panel media-original"><summary>Original {video?'video':'image'} · local file</summary>{video?<video src={url} controls preload="metadata" playsInline/>:<img src={url} alt="Original uploaded image"/>}</details>}
  </div>
}
