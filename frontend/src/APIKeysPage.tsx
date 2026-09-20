import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "./auth";
import type { APIKey } from "./auth";

export function APIKeysPage() {
  const { refreshAuth } = useAuth();
  const [keys, setKeys] = useState<APIKey[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyScopes, setNewKeyScopes] = useState<string[]>(["read"]);
  const [newKeyPlain, setNewKeyPlain] = useState("");

  const fetchKeys = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/api-keys", {
        credentials: "include",
      });
      if (response.ok) {
        const data = await response.json();
        setKeys(data);
      } else {
        setError("Failed to load API keys");
      }
    } catch {
      setError("Failed to load API keys");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const response = await fetch("/api/v1/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          name: newKeyName,
          scopes: newKeyScopes,
        }),
      });
      if (response.ok) {
        const data = await response.json();
        setNewKeyPlain(data.api_key);
        setShowCreate(false);
        setNewKeyName("");
        setNewKeyScopes(["read"]);
        await refreshAuth();
        fetchKeys();
      } else {
        const error = await response.json();
        setError(error.detail || "Failed to create API key");
      }
    } catch {
      setError("Failed to create API key");
    }
  };

  const handleDelete = async (keyId: string) => {
    if (!confirm("Delete this API key? This cannot be undone.")) return;
    try {
      const response = await fetch(`/api/v1/api-keys/${keyId}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (response.ok) {
        fetchKeys();
      } else {
        setError("Failed to delete API key");
      }
    } catch {
      setError("Failed to delete API key");
    }
  };

  const scopeOptions = [
    { value: "read", label: "Read" },
    { value: "write", label: "Write" },
    { value: "admin", label: "Admin" },
  ];

  return (
    <div className="settings-page">
      <div className="settings-container">
        <header className="settings-header">
          <h1>API Keys</h1>
          <p className="settings-description">
            Manage API keys for programmatic access. Keys are shown only once at creation.
          </p>
        </header>

        {newKeyPlain && (
          <div className="new-key-banner" role="alert">
            <h3>New API Key Created</h3>
            <p className="key-warning">Save this key now — it won't be shown again.</p>
            <div className="key-display">
              <code>{newKeyPlain}</code>
              <button
                type="button"
                className="copy-btn"
                onClick={() => {
                  navigator.clipboard.writeText(newKeyPlain);
                  alert("Copied to clipboard");
                }}
              >
                Copy
              </button>
            </div>
            <button className="btn" onClick={() => setNewKeyPlain("")}>
              I've saved it
            </button>
          </div>
        )}

        {error && <div className="error-banner" role="alert">{error}</div>}

        <section className="keys-section">
          <div className="section-header">
            <h2>Existing Keys</h2>
            <button className="btn btn-secondary" onClick={() => setShowCreate(true)}>
              Create New Key
            </button>
          </div>

          {showCreate && (
            <form onSubmit={handleCreate} className="create-form">
              <h3>Create New API Key</h3>
              <div className="field-group">
                <label htmlFor="key-name">Key Name</label>
                <input
                  type="text"
                  id="key-name"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder="e.g., Production Server"
                  required
                />
              </div>
              <div className="field-group">
                <label>Scopes</label>
                <div className="scope-options">
                  {scopeOptions.map((scope) => (
                    <label key={scope.value} className="scope-option">
                      <input
                        type="checkbox"
                        checked={newKeyScopes.includes(scope.value)}
                        onChange={(e) =>
                          e.target.checked
                            ? setNewKeyScopes([...newKeyScopes, scope.value])
                            : setNewKeyScopes(newKeyScopes.filter((s) => s !== scope.value))
                        }
                      />
                      <span>{scope.label}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="form-actions">
                <button type="button" className="btn" onClick={() => setShowCreate(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Create Key
                </button>
              </div>
            </form>
          )}

          {isLoading ? (
            <div className="loading">Loading keys…</div>
          ) : keys.length === 0 ? (
            <div className="empty-state">
              <p>No API keys yet.</p>
              <button className="btn btn-secondary" onClick={() => setShowCreate(true)}>
                Create your first key
              </button>
            </div>
          ) : (
            <table className="keys-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Scopes</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Last Used</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((key) => (
                  <tr key={key.id}>
                    <td>{key.name}</td>
                    <td>
                      <span className="scopes">
                        {key.scopes.map((s) => (
                          <span key={s} className="scope-badge">
                            {s}
                          </span>
                        ))}
                      </span>
                    </td>
                    <td>
                      <span className={`status-badge ${key.is_active ? "active" : "inactive"}`}>
                        {key.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td>{new Date(key.created_at).toLocaleDateString()}</td>
                    <td>{key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : "Never"}</td>
                    <td>
                      <button
                        className="btn btn-danger btn-sm"
                        onClick={() => handleDelete(key.id)}
                        disabled={!key.is_active}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  );
}

export default APIKeysPage;