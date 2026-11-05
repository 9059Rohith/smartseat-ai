import React, { useEffect, useState } from 'react'
import { Button, Icon, field, request } from './ui'
import { OperationsStatus } from './operations-status'

export function CloudLogin({ config, onLogin, recovery = false, onRecovered }) {
  const [mode, setMode] = useState(recovery ? 'reset' : 'signin')
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState(new URLSearchParams(location.search).has('auth_error') ? 'Sign-in could not finish. Please try again.' : '')
  const titles = { signin: 'Welcome back.', signup: 'Your restaurant starts here.', forgot: 'Recover your account.', reset: 'Choose a new password.' }
  return <main className="sign-in"><div className="login panel cloud-login">
    <div className="login-brand"><Icon name="chair" size={40}/><h1>SmartSeat AI</h1></div>
    <h2>{titles[mode]}</h2><p className="muted">Private workspace. Real restaurant data.</p>
    {config.google_enabled && ['signin','signup'].includes(mode) && <><Button onClick={()=>location.assign('/api/auth/google')}>Continue with Google</Button><p className="auth-divider">or continue with email</p></>}
    <form onSubmit={async e=>{
      e.preventDefault(); const form=e.currentTarget; setPending(true);setError('');setMessage('')
      const routes={signin:'sign-in',signup:'sign-up',forgot:'forgot-password',reset:'update-password'}
      try {
        const result=await request('/auth/'+routes[mode],'POST',{email:field(form,'email'),password:field(form,'password'),name:field(form,'name')})
        if(mode==='signin')onLogin(result)
        else if(result.user)onLogin(result.user)
        else if(mode==='reset'){history.replaceState(null,'','/');onRecovered?.()}
        else setMessage(result.message)
      } catch(e){setError(e.message)} finally{setPending(false)}
    }}>
      {mode==='signup'&&<label>Your name<input name="name" required maxLength={100} autoComplete="name"/></label>}
      {mode!=='reset'&&<label>Email address<input name="email" type="email" autoComplete="email" required maxLength={254}/></label>}
      {mode!=='forgot'&&<label>Password<input name="password" type="password" autoComplete={mode==='signin'?'current-password':'new-password'} minLength={mode==='signin'?1:12} maxLength={128} required/>{mode!=='signin'&&<small>Use at least 12 characters.</small>}</label>}
      {error&&<p className="error" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
      <Button variant="primary" type="submit" disabled={pending}>{pending?'Please wait…':({signin:'Sign in',signup:'Create account',forgot:'Send reset link',reset:'Update password'})[mode]}</Button>
    </form>
    {!recovery&&<div className="auth-links"><Button onClick={()=>{setMode(mode==='signup'?'signin':'signup');setError('');setMessage('')}}>{mode==='signup'?'Already have an account? Sign in':'Create an account'}</Button><Button onClick={()=>{setMode(mode==='forgot'?'signin':'forgot');setError('');setMessage('')}}>{mode==='forgot'?'Back to sign in':'Forgot password?'}</Button></div>}
    <small>Google sign-in identifies you. Connect your restaurant computer in Account to access its cameras.</small>
  </div></main>
}

export function Account({user,onUser}) {
  const [events,setEvents]=useState([]), [pending,setPending]=useState(false), [message,setMessage]=useState(''), [error,setError]=useState('')
  useEffect(()=>{let active=true;request('/auth/account').then(data=>{if(active)setEvents(data.events)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[])
  async function save(path,body,success){setPending(true);setError('');setMessage('');try{await request(path,'POST',body);onUser(await request('/me'));setMessage(success);return true}catch(e){setError(e.message);return false}finally{setPending(false)}}
  return <div className="stack account-page">
    <section className="panel"><div className="panel-head"><h2>Your account</h2><small>{user.provider==='google'?'Google account':'Email account'} · {user.email_verified?'Verified':'Verification pending'}</small></div>
      <p>{user.email}</p><form key={user.id} onSubmit={e=>{e.preventDefault();save('/auth/update-account',{name:field(e.currentTarget,'name'),workspace_name:field(e.currentTarget,'workspace_name')},'Account saved.')}}>
        <div className="two"><label>Your name<input name="name" defaultValue={user.name} required maxLength={100}/></label><label>Restaurant name<input name="workspace_name" defaultValue={user.workspace.name} required maxLength={100}/></label></div>
        <Button type="submit" variant="primary" disabled={pending}>Save account</Button>
      </form>
    </section>
    <section className="panel"><div className="panel-head"><h2>Restaurant connection</h2><small>{user.engine_access?'Credentials connected':'Connect your restaurant computer'}</small></div>
      <p>The restaurant computer runs camera detection. Use its manager or staff credentials to access the real floor, cameras and operations. Account sign-in does not grant camera access by itself.</p>
      {user.engine_access?<Button disabled={pending} onClick={()=>save('/auth/disconnect-engine',{},'Restaurant disconnected from this session.')}>Disconnect restaurant</Button>:<form onSubmit={async e=>{e.preventDefault();const form=e.currentTarget;if(await save('/auth/connect-engine',{name:field(form,'engine_name'),password:field(form,'engine_password')},'Restaurant connected. Open Floor to view real activity.'))form.reset()}}>
        <div className="two"><label>Restaurant username<input name="engine_name" autoComplete="off" required maxLength={100}/></label><label>Restaurant password<input name="engine_password" type="password" autoComplete="off" required maxLength={160}/></label></div><Button type="submit" variant="primary" disabled={pending}>{pending?'Connecting…':'Connect restaurant'}</Button>
      </form>}
      <small>Keep the restaurant computer and its public connector online. Saved reports remain available when it disconnects.</small>
    </section>
    {error&&<p className="error" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    {user.engine_access&&user.role==='manager'&&<OperationsStatus/>}
    <section className="panel"><div className="panel-head"><h2>Account activity</h2><small>Recent workspace actions</small></div>{events.length?<ul>{events.map((event,index)=><li key={index}>{event.event.replaceAll('_',' ')} · {new Date(event.created_at).toLocaleString()}</li>)}</ul>:<p>No account activity recorded yet.</p>}</section>
  </div>
}
