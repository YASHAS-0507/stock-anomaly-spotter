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
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Login failed");
      }
      router.push("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page" style={{ maxWidth: 380, paddingTop: 120 }}>
      <div className="header" style={{ display: "block", marginBottom: 32 }}>
        <div className="title">Stock anomaly spotter</div>
        <div className="subtitle">Sign in to continue</div>
      </div>

      <form onSubmit={handleSubmit} className="panel">
        <div style={{ marginBottom: 16 }}>
          <label className="card-label" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ width: "100%", marginTop: 6 }}
            autoFocus
          />
        </div>
        {error && (
          <div style={{ color: "#f87171", fontSize: 13, marginBottom: 16 }}>{error}</div>
        )}
        <button type="submit" disabled={loading} style={{ width: "100%" }}>
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}
