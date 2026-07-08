import { useState } from "react";
import { useAuth } from "../auth";
import { login as apiLogin, register as apiRegister } from "../api";

export default function Login() {
  const { login, authRequired, brand } = useAuth();
  const displayName = brand?.display_name || "Lead Generator";
  const productName = brand?.product_name || "Lead Generator";
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result =
        mode === "login"
          ? await apiLogin(email, password)
          : await apiRegister(email, password, name);
      login(result.access_token, result.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card card">
        <div className="brand">{displayName}</div>
        <h1>{productName}</h1>
        <p className="login-subtitle">
          {authRequired
            ? "Sign in to access the lead pipeline."
            : "Sign in (optional in local dev)."}
        </p>

        {error && <div className="alert alert-error">{error}</div>}

        <form onSubmit={submit}>
          {mode === "register" && (
            <div>
              <label>Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                autoComplete="name"
              />
            </div>
          )}
          <div>
            <label>Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </div>
          <div>
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
            />
          </div>
          <button className="btn" type="submit" disabled={loading}>
            {loading ? "Please wait..." : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        <p className="login-toggle">
          {mode === "login" ? (
            <>
              Need an account?{" "}
              <button type="button" className="link-btn" onClick={() => setMode("register")}>
                Register
              </button>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <button type="button" className="link-btn" onClick={() => setMode("login")}>
                Sign in
              </button>
            </>
          )}
        </p>
      </div>
    </div>
  );
}
