import { useState } from "react";
import { useRouter } from "next/router";

export default function Login() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!res.ok) throw new Error((await res.json()).error || "Incorrect password");
      router.push("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-box">
        <div className="login-logo">
          <div className="brand-dot" />
          <div className="login-title">STOCK ANOMALY SPOTTER</div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="login-field">
            <label className="login-label" htmlFor="pw">Access key</label>
            <input
              id="pw"
              type="password"
              className="login-input"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoFocus
              placeholder="••••••••"
            />
          </div>

          {error && <div className="login-error">⚠ {error}</div>}

          <button type="submit" className="btn-login" disabled={loading}>
            {loading ? "VERIFYING..." : "ENTER"}
          </button>
        </form>
      </div>
    </div>
  );
}