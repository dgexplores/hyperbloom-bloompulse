import React, { useState, useRef } from "react";
import { useAuth } from "./auth";
import { useNavigate, useLocation } from "react-router-dom";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);

  const from = (location.state as any)?.from?.pathname || "/";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-card">
          <div className="login-header">
            <h1 className="wordmark">
              Bloom<span className="pulse">Pulse</span>
            </h1>
            <p className="login-tagline">
              Load a sensor CSV. Every reading is charted against the limits that
              govern it, and every claim below carries the passage it came from.
            </p>
          </div>

          {error && (
            <div className="login-error" role="alert">
              <span className="error-icon" aria-hidden="true">⚠</span>
              <span>{error}</span>
            </div>
          )}

          <form ref={formRef} onSubmit={handleSubmit} className="login-form" noValidate>
            <div className="field-group">
              <label htmlFor="email" className="field-label">Email</label>
              <input
                type="email"
                id="email"
                name="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                required
                disabled={isLoading}
                className="field-input"
              />
            </div>

            <div className="field-group">
              <label htmlFor="password" className="field-label">Password</label>
              <div className="password-wrapper">
                <input
                  type={showPassword ? "text" : "password"}
                  id="password"
                  name="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  disabled={isLoading}
                  className="field-input"
                />
                <button
                  type="button"
                  className="password-toggle"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  disabled={isLoading}
                >
                  {showPassword ? "🙈" : "👁"}
                </button>
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary btn-block"
              disabled={isLoading}
            >
              {isLoading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <div className="login-divider">
            <span>or</span>
          </div>

          <button
            type="button"
            className="btn btn-google"
            onClick={() => {
              window.location.href = "/api/v1/auth/google";
            }}
          >
            <svg className="google-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.9-3.81c-.78.54-1.79.85-3.02.85-3.08 0-5.48-2.05-6.32-4.8H2.88v3.33h8.29c.95 2.34 3.46 4.09 6.35 4.09 2.08 0 3.93-.69 5.22-1.88l3.23 3.23c-2.18 2.3-5.22 3.71-8.73 3.71z"
              />
              <path
                fill="#FBBC05"
                d="M5.62 14.43c-.27-.56-.42-1.18-.42-1.83s.15-1.27.42-1.83V8.7h-3.17c-.67.99-1.04 2.18-1.04 3.56s.37 2.57 1.04 3.56l3.5 2.54zm8.48 3.8c.88-1.07 1.4-2.41 1.4-3.94s-.52-2.87-1.4-3.94l-3.4-2.53c-.98 1.28-2.2 2.31-3.7 2.31-3.46 0-6.34-2.35-7.35-5.5H1.49v3.19c1.04 1.6 2.68 2.93 4.65 2.93 2.05 0 3.88-.71 5.17-1.94l3.4 2.46c-1.9 2.02-4.54 3.27-7.5 3.27-4.55 0-8.28-3.1-8.28-6.9s3.73-6.9 8.28-6.9c3.46 0 6.1 2.22 7.25 5.04l2.9-2.8C17.3 5.6 14.9 4 12 4c-4.97 0-9 4.03-9 9s4.03 9 9 9c2.28 0 4.19-.81 5.66-2.14l-2.9 2.74z"
              />
              <path
                fill="#EA4335"
                d="M5.62 14.43c-.27-.56-.42-1.18-.42-1.83s.15-1.27.42-1.83V8.7h-3.17c-.67.99-1.04 2.18-1.04 3.56s.37 2.57 1.04 3.56l3.5 2.54zm8.48 3.8c.88-1.07 1.4-2.41 1.4-3.94s-.52-2.87-1.4-3.94l-3.4-2.53c-.98 1.28-2.2 2.31-3.7 2.31-3.46 0-6.34-2.35-7.35-5.5H1.49v3.19c1.04 1.6 2.68 2.93 4.65 2.93 2.05 0 3.88-.71 5.17-1.94l3.4 2.46c-1.9 2.02-4.54 3.27-7.5 3.27-4.55 0-8.28-3.1-8.28-6.9s3.73-6.9 8.28-6.9c3.46 0 6.1 2.22 7.25 5.04l2.9-2.8C17.3 5.6 14.9 4 12 4c-4.97 0-9 4.03-9 9s4.03 9 9 9c2.28 0 4.19-.81 5.66-2.14l-2.9 2.74z"
              />
            </svg>
            <span>Continue with Google</span>
          </button>

          <p className="login-footer">
            Don't have an account? <a href="/register">Create one</a>
          </p>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;