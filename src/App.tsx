import { useState, type FormEvent } from 'react'
import './App.css'

function CrossIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 5v14M5 12h14"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
    </svg>
  )
}

function App() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
  }

  return (
    <main className="login">
      <div className="login__ambient" aria-hidden="true" />

      <section className="login__shell" aria-label="Sign in to FedHeal">
        <aside className="login__visual">
          <div className="login__brand">
            <span className="login__mark">
              <CrossIcon />
            </span>
            <span className="login__brand-name">FedHeal</span>
          </div>

          <div className="login__copy">
            <h1>Care that stays with you.</h1>
            <p>
              Secure access to your health records, care team, and coverage —
              in one calm place.
            </p>
          </div>
        </aside>

        <div className="login__panel">
          <header className="login__panel-header">
            <h2>Welcome back</h2>
            <p>Sign in to continue to your FedHeal account.</p>
          </header>

          <form className="login__form" onSubmit={handleSubmit}>
            <div className="field">
              <label htmlFor="username">Username</label>
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                placeholder="Enter your username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                required
              />
            </div>

            <div className="field">
              <div className="field__top">
                <label htmlFor="password">Password</label>
                <a className="field__link" href="#forgot">
                  Forgot password?
                </a>
              </div>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                placeholder="Enter your password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>

            <div className="login__actions">
              <button className="btn btn--primary" type="submit">
                Sign in
              </button>
            </div>
          </form>

          <p className="login__meta">
            New to FedHeal? <a href="#signup">Create an account</a>
          </p>
        </div>
      </section>
    </main>
  )
}

export default App
