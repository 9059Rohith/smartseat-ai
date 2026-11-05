import React, { memo, useCallback, useEffect, useRef, useState } from 'react'

export const backgrounds = Array.from({ length: 24 }, (_, index) => '/assets/backgrounds/scene-' + String(index).padStart(2, '0') + '.webp')

export function useAtmosphere(page, ready) {
  const [reduced, setReduced] = useState(() => matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [paused, setPaused] = useState(() => { try { return localStorage.getItem('smartseat-motion') === 'off' } catch { return false } })
  const [scene, setScene] = useState(0)
  const stopped = reduced || paused
  const toggle = useCallback(() => setPaused(value => !value), [])
  const next = useCallback(() => setScene(value => (value + 1) % backgrounds.length), [])
  useEffect(() => { window.scrollTo({ top:0, left:0, behavior:'instant' }) }, [page])
  useEffect(() => {
    const media = matchMedia('(prefers-reduced-motion: reduce)')
    const change = () => setReduced(media.matches)
    media.addEventListener('change', change)
    return () => media.removeEventListener('change', change)
  }, [])
  useEffect(() => {
    document.documentElement.dataset.motion = stopped ? 'off' : 'on'
    try { localStorage.setItem('smartseat-motion', paused ? 'off' : 'on') } catch { /* Storage can be unavailable. */ }
  }, [stopped, paused])
  useEffect(() => {
    const update = () => { document.documentElement.dataset.visibility = document.hidden ? 'hidden' : 'visible' }
    update(); document.addEventListener('visibilitychange',update)
    return () => document.removeEventListener('visibilitychange',update)
  }, [])
  useEffect(() => {
    if (stopped) return
    const timer = setInterval(() => { if (!document.hidden) next() }, 20000)
    return () => clearInterval(timer)
  }, [stopped, next])
  useEffect(() => {
    let frame = 0
    function update() {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const max = document.documentElement.scrollHeight - innerHeight
        document.documentElement.style.setProperty('--scroll-progress', max > 0 ? Math.min(1, scrollY / max) : 0)
        document.documentElement.style.setProperty('--scene-offset', stopped ? '0px' : Math.min(scrollY * .10, 70) + 'px')
      })
    }
    update()
    addEventListener('scroll', update, { passive: true }); addEventListener('resize', update)
    return () => { removeEventListener('scroll', update); removeEventListener('resize', update); cancelAnimationFrame(frame) }
  }, [stopped, page, ready])
  useEffect(() => {
    if (stopped || !ready) return
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) { entry.target.classList.add('revealed'); observer.unobserve(entry.target) }
    }), { threshold: .06 })
    document.querySelectorAll('.workspace .panel, .workspace .metric').forEach((node, index) => {
      node.dataset.reveal = 'true'; node.style.setProperty('--reveal-delay', Math.min(index % 4 * 60, 180) + 'ms'); observer.observe(node)
    })
    return () => observer.disconnect()
  }, [page, ready, stopped])
  useEffect(() => {
    // Load only the next photograph; the whole collection is never downloaded at once.
    const image = new Image(); image.src = backgrounds[(scene + 1) % backgrounds.length]
  }, [scene])
  return { stopped, reduced, toggle, next, scene }
}

export const Atmosphere = memo(function Atmosphere({ scene }) {
  const previous = useRef(scene)
  useEffect(() => { previous.current = scene }, [scene])
  return <div className="ambience" aria-hidden="true">
    <div className="ambience-previous" style={{ backgroundImage: `url("${backgrounds[previous.current]}")` }}/>
    <div className="ambience-photo" key={scene} style={{ backgroundImage: `url("${backgrounds[scene]}")` }}/>
    <div className="ambience-shade"/><div className="ambient-glow"/><div className="ambient-grain"/>
  </div>
})

export function AnimatedTitle({ children }) {
  return <h1 className="display-title" aria-label={children}>{children.split(' ').map((word, index) =>
    <span className="title-mask" key={index}><span style={{ '--word-delay': index * 90 + 'ms' }}>{word}</span>{' '}</span>)}</h1>
}

export function MotionControls({ stopped, reduced, toggle, next }) {
  return <div className="motion-controls">
    <button className="icon-button" type="button" onClick={next} aria-label="Next background" title="Next background"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="4"/><path d="m4 17 5-5 4 4 3-7 5 8"/><circle cx="8" cy="8" r="1"/></svg></button>
    <button className="icon-button" type="button" onClick={toggle} disabled={reduced} aria-label={stopped ? 'Enable animations' : 'Pause animations'} aria-pressed={stopped} title={reduced ? 'Reduced motion follows your system setting' : stopped ? 'Enable animations' : 'Pause animations'}>
      {stopped ? <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m9 5 10 7-10 7z"/></svg> : <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M8 5v14M16 5v14"/></svg>}
    </button>
  </div>
}
