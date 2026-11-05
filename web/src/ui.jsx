import React, { createContext, useContext, useEffect, useRef } from 'react'

const shapes = {
  media: <><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 6-6 4 4 3-3 5 5"/></>,
  chair: <><path d="M6 13V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v7M4 14h16v3H4zM6 17v4m12-4v4"/></>,
  floor: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  people: <><circle cx="9" cy="7" r="3"/><path d="M3 20v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3m2-16a3 3 0 0 1 0 6m2 3a4 4 0 0 1 3 4v3"/></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 8-3 8-3 10h18c0-2-3-2-3-10m-8 13a2 2 0 0 0 4 0"/></>,
  clean: <><path d="m14 3 2.4 5.6L22 11l-5.6 2.4L14 19l-2.4-5.6L6 11l5.6-2.4L14 3Zm-9 9 1.3 3.7L10 17l-3.7 1.3L5 22l-1.3-3.7L0 17l3.7-1.3L5 12Z"/></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/></>,
  analytics: <><path d="M4 20V12h3v8zm7 0V8h3v12zm7 0V3h3v17z"/></>,
  camera: <><rect x="2" y="5" width="14" height="14" rx="2"/><path d="m16 10 6-4v12l-6-4"/></>,
  plus: <path d="M12 5v14M5 12h14"/>,
  expand: <path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6"/>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="m10 2-.6 3-2 .9-2.6-1.6-2.5 2.5L4 9.4l-.9 2L0 12v3l3 .6.9 2-1.6 2.6 2.5 2.5L7.4 21l2 .9.6 3h4l.6-3 2-.9 2.6 1.6 2.5-2.5-1.6-2.6.9-2 3-.6v-3l-3-.6-.9-2 1.6-2.6-2.5-2.5-2.6 1.6-2-.9L14 2z" transform="translate(2 0) scale(.83)"/></>,
  screen: <><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M12 17v4m-5 0h10"/></>,
  close: <path d="m6 6 12 12M18 6 6 18"/>,
  check: <path d="m4 12 5 5 11-11"/>,
  logout: <path d="M9 3H4v18h5m5-5 5-4-5-4m5 4H8"/>,
  replay: <path d="M20 11a8 8 0 1 0-2 6M20 4v7h-7"/>,
}
export function Icon({ name, size = 20 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shapes[name]}</svg>
}

export const labels = { available: 'Available', occupied: 'Occupied', waiting: 'Needs service', cleaning: 'Needs cleaning', reserved: 'Reserved', unknown: 'Unknown' }
export const eventLabels = { occupied: 'Party seated', cleaning: 'Guests departed', cleaned: 'Cleaning confirmed', greeted: 'Greeting confirmed', service_due: 'Greeting overdue', party_joined: 'Party joined the waitlist', table_ready: 'Party called to a table', party_seated: 'Waitlist party seated', reserved: 'Reservation booked', reservation_cancelled: 'Reservation cancelled', reservation_seated: 'Reservation seated', entry: 'Entrance crossing' }
export const cameraLabels = { idle: 'Stopped', starting: 'Connecting', stopping: 'Closing', live: 'Live', reconnecting: 'Reconnecting', obscured: 'View blocked or dark', complete: 'Sample finished', error: 'Camera error' }
export function duration(seconds) {
  if (seconds == null) return '—'
  const s = Math.max(0, Math.floor(seconds))
  if (s < 60) return s + 's'
  if (s < 3600) return Math.floor(s / 60) + 'm ' + s % 60 + 's'
  return Math.floor(s / 3600) + 'h ' + Math.floor(s % 3600 / 60) + 'm'
}
export const stamp = seconds => new Date(seconds * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
export const field = (form, name) => new FormData(form).get(name)
export function Status({ state }) { return <span className={'status ' + state}><span/>{labels[state]}</span> }
export function Button({ children, variant, icon, ...props }) {
  return <button className={'button ' + (variant || '')} {...props}>{icon && <Icon name={icon} size={16}/>} {children}</button>
}
export function Empty({ icon, children }) {
  return <div className="empty">{icon && <Icon name={icon} size={24}/>}<p>{children}</p></div>
}
export const NoticeContext = createContext(null)
export function Modal({ title, children, close }) {
  const ref = useRef(null)
  const notice = useContext(NoticeContext)
  useEffect(() => { ref.current.showModal() }, [])
  return <dialog ref={ref} onCancel={close} aria-label={title}>
    <div className="dialog-head"><h2>{title}</h2><button className="icon-button" onClick={close} aria-label="Close dialog"><Icon name="close"/></button></div>
    {notice?.error && <p className="error dialog-error" role="alert">{notice.message}</p>}
    {children}
  </dialog>
}

export async function request(path, method = 'GET', body) {
  const response = await fetch('/api' + path, { method, headers: body === undefined ? {} : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) })
  let data
  try { data = await response.json() } catch { throw new Error('Restaurant engine is unavailable. Keep the restaurant computer online.') }
  if (!response.ok) {
    const message = Array.isArray(data.detail) ? data.detail.map(issue => issue.msg).join(' ') : data.detail
    throw Object.assign(new Error(message || 'The request could not be completed.'), { status: response.status })
  }
  return data
}
