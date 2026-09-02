import { useMemo, useState } from "react";

// A quiet field of fixed stars behind the login card. Generated once per
// mount with a seeded-feeling spread so it doesn't look like a repeating
// texture. Purely decorative — respects prefers-reduced-motion via the
// "soft-pulse" keyframe being disabled globally.
function useStarfield(count = 90) {
  return useMemo(
    () =>
      Array.from({ length: count }, (_, i) => ({
        id: i,
        x: Math.random() * 100,
        y: Math.random() * 100,
        r: Math.random() * 1.6 + 0.4,
        delay: Math.random() * 4,
      })),
    [count]
  );
}

export default function LoginGate({ onLogin, authApiBase, busy, error }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const stars = useStarfield();

  function handleSubmit(e) {
    e.preventDefault();
    if (!email || !password) return;
    onLogin(email, password);
  }

  return (
    <div className="login-gate">
      <svg className="login-gate__stars" aria-hidden="true">
        {stars.map((s) => (
          <circle
            key={s.id}
            cx={`${s.x}%`}
            cy={`${s.y}%`}
            r={s.r}
            fill="#cfe3f5"
            style={{
              animation: `soft-pulse ${4 + s.delay}s ease-in-out infinite`,
              animationDelay: `${s.delay}s`,
            }}
          />
        ))}
      </svg>

      <div className="login-gate__card glass">
        <div className="login-gate__mark" aria-hidden="true">
          <span className="login-gate__orbit" />
          <span className="login-gate__core" />
        </div>

        <p className="eyebrow">Federated Learning · Healthcare</p>
        <h1 className="login-gate__title">FedHeal</h1>
        <p className="login-gate__sub">
          Sign in with your hospital's credentials. Your patient data never
          leaves this session — only your login token does.
        </p>

        <form onSubmit={handleSubmit} className="login-gate__form">
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@hospital.org"
              required
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </label>

          {error && <p className="login-gate__error">{error}</p>}

          <button type="submit" className="btn btn--primary" disabled={busy}>
            {busy ? "Signing in…" : "Enter the federation"}
          </button>
        </form>

        <p className="login-gate__api mono">talking to {authApiBase}</p>
      </div>
    </div>
  );
}
