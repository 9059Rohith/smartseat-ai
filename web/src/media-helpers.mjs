export const mediaStates = {
  occupied: {label:'In use',color:'#fb7185'},
  items_present: {label:'Items remain',color:'#fbbf24'},
  looks_clear: {label:'Looks clear',color:'#86efac'},
  unknown: {label:'Unverified',color:'#a8b3bd'},
}

export function sampleTimes(duration) {
  if (!Number.isFinite(duration) || duration<=0 || duration>600) throw new Error('Choose a video up to 10 minutes long.')
  const count=Math.min(120,Math.ceil(duration))
  return Array.from({length:count},(_,i)=>Number((i*duration/count).toFixed(4)))
}

export function mediaTime(seconds) {
  return Math.floor(seconds/60)+':'+(seconds%60).toFixed(2).padStart(5,'0')
}

export function mediaCSV(results) {
  const header=['source_seconds','table_candidates','people','chairs','in_use','items_remain','looks_clear','unverified']
  return [header.join(','),...results.map(({frame_time,summary:s})=>
    [frame_time,s.tables,s.people,s.chairs,s.occupied,s.items_present,s.looks_clear,s.unknown].join(','))].join('\n')+'\n'
}

export function saveBlob(blob,name) {
  const url=URL.createObjectURL(blob),link=document.createElement('a')
  link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
}

export function waitForMedia(element,event,signal,action) {
  return new Promise((resolve,reject)=>{
    if(signal.aborted){reject(new DOMException('Stopped','AbortError'));return}
    let timer
    const cleanup=()=>{clearTimeout(timer);element.removeEventListener(event,done);element.removeEventListener('error',failed);signal.removeEventListener('abort',aborted)}
    const done=()=>{cleanup();resolve()}
    const failed=()=>{cleanup();reject(new Error('This browser cannot decode that file. Try a JPEG, PNG, WebP, MP4 (H.264) or WebM.'))}
    const aborted=()=>{cleanup();reject(new DOMException('Stopped','AbortError'))}
    element.addEventListener(event,done,{once:true});element.addEventListener('error',failed,{once:true});signal.addEventListener('abort',aborted,{once:true})
    timer=setTimeout(()=>{cleanup();reject(new Error('The media could not be decoded in time. Try a smaller file or another format.'))},20000)
    try{action()}catch(error){cleanup();reject(error)}
  })
}
