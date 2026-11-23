import { useState } from "react";
import { login } from "../api";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      onLogin(await login(username, password));
    } catch (err) {
      const msg = err.message.startsWith("429")
        ? "Too many failed attempts. Wait a few minutes and try again."
        : "Wrong username or password.";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <form className="card login" onSubmit={submit}>
        <h1>FreshTrack</h1>
        <p className="muted">Sign in to see stock, forecasts and recommendations.</p>
        <label>
          Username
          <input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <button type="submit" disabled={busy}>{busy ? "Signing in..." : "Sign in"}</button>
        {error && <p className="error" role="alert">{error}</p>}
      </form>
    </div>
  );
}
