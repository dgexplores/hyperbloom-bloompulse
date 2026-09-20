import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, NavLink, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { ProtectedRoute } from "./ProtectedRoute";
import { LoginPage } from "./LoginPage";
import { APIKeysPage } from "./APIKeysPage";
import { OrganizationPage } from "./OrganizationPage";
import AnalyzerApp from "./Analyzer";
import "./styles.css";

function AppContent() {
  const { isAuthenticated } = useAuth();
  const [showLogin, setShowLogin] = useState(false);

  return (
    <div className="app-wrapper">
      <header className="global-header">
        <nav className="nav" aria-label="Primary">
          <div className="nav-brand">
            <NavLink to="/" className="brand">
              Bloom<span className="pulse">Pulse</span>
            </NavLink>
          </div>
          <div className="nav-links">
            <NavLink to="/" className="nav-link">Analyse</NavLink>
            {isAuthenticated && (
              <>
                <NavLink to="/assets" className="nav-link">Assets</NavLink>
                <NavLink to="/api-keys" className="nav-link">API Keys</NavLink>
              </>
            )}
          </div>
          <div className="nav-auth">
            {isAuthenticated ? (
              <UserMenu />
            ) : (
              <button className="btn btn-secondary" onClick={() => setShowLogin(true)}>
                Sign in
              </button>
            )}
          </div>
        </nav>
      </header>
      <main className="main-content">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<AnalyzerApp />} />
          <Route
            path="/assets"
            element={
              <ProtectedRoute allowedRoles={["admin", "engineer"]}>
                <OrganizationPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/api-keys"
            element={
              <ProtectedRoute allowedRoles={["admin", "engineer"]}>
                <APIKeysPage />
              </ProtectedRoute>
            }
          />
          <Route path="/unauthorized" element={<Unauthorized />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        {showLogin && <LoginModal onClose={() => setShowLogin(false)} />}
      </main>
    </div>
  );
}

function UserMenu() {
  const { user, organization, logout, isAuthenticated } = useAuth();

  if (!isAuthenticated) return null;

  return (
    <div className="user-menu">
      <div className="user-avatar" aria-label="User menu">
        {user?.name?.charAt(0).toUpperCase() || user?.email?.charAt(0).toUpperCase() || "U"}
      </div>
      <div className="user-dropdown">
        <div className="user-info">
          <span className="user-name">{user?.name || user?.email}</span>
          <span className="user-email">{user?.email}</span>
        </div>
        <hr />
        <div className="org-info">
          <small>Organization: {organization?.name}</small>
        </div>
        <hr />
        <button className="dropdown-item" onClick={logout}>
          Sign out
        </button>
      </div>
    </div>
  );
}

function Unauthorized() {
  return (
    <div className="unauthorized-page">
      <h1>403 — Unauthorized</h1>
      <p>You don't have permission to access this page.</p>
      <p>Contact your administrator if you believe this is an error.</p>
      <NavLink to="/" className="btn btn-primary">
        Go home
      </NavLink>
    </div>
  );
}

function LoginModal({ onClose }: { onClose: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal login-modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Close">
          ✕
        </button>
        <h2>Sign in</h2>
        <form onSubmit={(e) => { e.preventDefault(); onClose(); }}>
          <div className="field-group">
            <label htmlFor="modal-email">Email</label>
            <input
              type="email"
              id="modal-email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              required
            />
          </div>
          <div className="field-group">
            <label htmlFor="modal-password">Password</label>
            <div className="password-wrapper">
              <input
                type={showPassword ? "text" : "password"}
                id="modal-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? "🙈" : "👁"}
              </button>
            </div>
          </div>
          <button type="submit" className="btn btn-primary btn-block">
            Sign in
          </button>
        </form>
        <div className="login-divider"><span>or</span></div>
        <button className="btn btn-google">Continue with Google</button>
      </div>
    </div>
  );
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;

const container = document.getElementById("root");
if (container) {
  createRoot(container).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}
