import { useState } from 'react';
import { ArrowRight, Route } from 'lucide-react';
import { getErrorMessage } from '../api_services.js';
import { useAccess } from '../context/AccessContext.jsx';

export default function AuthPage() {
  const { signIn, signUp, notice } = useAccess();
  const [mode, setMode] = useState('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const registering = mode === 'register';

  async function submit(event) {
    event.preventDefault();
    setError('');
    if (registering && password !== confirmation) {
      setError('The passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      const credentials = { username: username.trim(), password };
      if (registering) await signUp(credentials);
      else await signIn(credentials);
    } catch (issue) {
      setError(getErrorMessage(issue));
    } finally {
      setBusy(false);
    }
  }

  function changeMode(nextMode) {
    setMode(nextMode);
    setError('');
  }

  return <main className="auth-screen">
    <section className="auth-card">
      <div className="auth-brand"><span className="brand-mark"><Route size={19} /></span><span><strong>routewise</strong><small>DELIVERY OPERATIONS</small></span></div>
      <div className="auth-heading"><div className="eyebrow">YOUR DELIVERY WORKSPACE</div><h1>{registering ? 'Create your account' : 'Welcome back'}</h1><p>{registering ? 'Create an account to access your delivery workspace.' : 'Log in to continue to your delivery workspace.'}</p></div>
      <div className="auth-tabs" role="tablist" aria-label="Account access">
        <button type="button" role="tab" aria-selected={!registering} className={!registering ? 'active' : ''} onClick={() => changeMode('login')}>Log in</button>
        <button type="button" role="tab" aria-selected={registering} className={registering ? 'active' : ''} onClick={() => changeMode('register')}>Create account</button>
      </div>
      <form className="auth-form" onSubmit={submit}>
        <label className="field-label" htmlFor="auth-username">Username</label>
        <input id="auth-username" className="auth-input" autoComplete="username" minLength={3} maxLength={32} pattern="[A-Za-z0-9_.-]+" required value={username} onChange={(event) => setUsername(event.target.value)} />
        <label className="field-label" htmlFor="auth-password">Password</label>
        <input id="auth-password" className="auth-input" type="password" autoComplete={registering ? 'new-password' : 'current-password'} minLength={10} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} />
        {registering && <>
          <label className="field-label" htmlFor="auth-confirm-password">Confirm password</label>
          <input id="auth-confirm-password" className="auth-input" type="password" autoComplete="new-password" minLength={10} maxLength={128} required value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
          <p className="auth-help">New accounts receive the carrier / warehouse operator role.</p>
        </>}
        {(error || notice) && <div className="auth-error" role="alert">{error || notice}</div>}
        <button className="button primary auth-submit" disabled={busy}>{busy ? <span className="mini-spinner light" /> : <ArrowRight size={16} />}{busy ? 'Please wait…' : registering ? 'Create account' : 'Log in'}</button>
      </form>
    </section>
  </main>;
}
