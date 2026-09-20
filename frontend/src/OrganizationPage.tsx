import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "./auth";
import type { Asset } from "./auth";

export function OrganizationPage() {
  const { organization, refreshAuth, user } = useAuth();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreateAsset, setShowCreateAsset] = useState(false);
  const [newAsset, setNewAsset] = useState({ name: "", rpm: 1750, bearing_type: "6205" });

  const fetchAssets = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/assets", {
        credentials: "include",
      });
      if (response.ok) {
        const data = await response.json();
        setAssets(data);
      } else {
        setError("Failed to load assets");
      }
    } catch {
      setError("Failed to load assets");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAssets();
  }, [fetchAssets]);

  const handleCreateAsset = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const response = await fetch("/api/v1/assets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(newAsset),
      });
      if (response.ok) {
        await refreshAuth();
        fetchAssets();
        setShowCreateAsset(false);
        setNewAsset({ name: "", rpm: 1750, bearing_type: "6205" });
      } else {
        const err = await response.json();
        setError(err.detail || "Failed to create asset");
      }
    } catch {
      setError("Failed to create asset");
    }
  };

  const handleDeleteAsset = async (assetId: string) => {
    if (!confirm("Delete this asset? This cannot be undone.")) return;
    try {
      const response = await fetch(`/api/v1/assets/${assetId}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (response.ok) {
        fetchAssets();
      } else {
        setError("Failed to delete asset");
      }
    } catch {
      setError("Failed to delete asset");
    }
  };

  return (
    <div className="settings-page">
      <div className="settings-container">
        <header className="settings-header">
          <h1>Organization: {organization?.name || "Loading…"}</h1>
          <p className="settings-description">
            Manage your organization's assets and settings.
          </p>
        </header>

        {error && <div className="error-banner" role="alert">{error}</div>}

        <section className="org-info-section">
          <h2>Organization Details</h2>
          <dl className="info-grid">
            <div>
              <dt>Name</dt>
              <dd>{organization?.name}</dd>
            </div>
            <div>
              <dt>Slug</dt>
              <dd>{organization?.slug}</dd>
            </div>
            <div>
              <dt>Subscription Tier</dt>
              <dd>
                <span className="tier-badge">{organization?.subscription_tier}</span>
              </dd>
            </div>
            <div>
              <dt>Your Role</dt>
              <dd>
                <span className="role-badge">{user?.role}</span>
              </dd>
            </div>
          </dl>
        </section>

        <section className="assets-section">
          <div className="section-header">
            <h2>Assets ({assets.length})</h2>
            <button className="btn btn-secondary" onClick={() => setShowCreateAsset(true)}>
              Add Asset
            </button>
          </div>

          {showCreateAsset && (
            <form onSubmit={handleCreateAsset} className="create-form">
              <h3>Add New Asset</h3>
              <div className="field-group">
                <label htmlFor="asset-name">Asset Name</label>
                <input
                  type="text"
                  id="asset-name"
                  value={newAsset.name}
                  onChange={(e) => setNewAsset({ ...newAsset, name: e.target.value })}
                  placeholder="e.g., Main Compressor BRG-05"
                  required
                />
              </div>
              <div className="field-row">
                <div className="field-group">
                  <label htmlFor="asset-rpm">RPM</label>
                  <input
                    type="number"
                    id="asset-rpm"
                    value={newAsset.rpm}
                    onChange={(e) => setNewAsset({ ...newAsset, rpm: parseInt(e.target.value) })}
                    min={1}
                    max={100000}
                    required
                  />
                </div>
                <div className="field-group">
                  <label htmlFor="asset-bearing">Bearing Type</label>
                  <select
                    id="asset-bearing"
                    value={newAsset.bearing_type}
                    onChange={(e) => setNewAsset({ ...newAsset, bearing_type: e.target.value })}
                    required
                  >
                    <option value="6205">6205 (Deep Groove)</option>
                    <option value="6206">6206 (Deep Groove)</option>
                    <option value="6207">6207 (Deep Groove)</option>
                    <option value="6305">6305 (Deep Groove)</option>
                    <option value="6306">6306 (Deep Groove)</option>
                    <option value="NU205">NU205 (Cylindrical Roller)</option>
                    <option value="NU206">NU206 (Cylindrical Roller)</option>
                    <option value="other">Other (specify in name)</option>
                  </select>
                </div>
              </div>
              <div className="form-actions">
                <button type="button" className="btn" onClick={() => setShowCreateAsset(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Add Asset
                </button>
              </div>
            </form>
          )}

          {isLoading ? (
            <div className="loading">Loading assets…</div>
          ) : assets.length === 0 ? (
            <div className="empty-state">
              <p>No assets registered yet.</p>
              <button className="btn btn-secondary" onClick={() => setShowCreateAsset(true)}>
                Add your first asset
              </button>
            </div>
          ) : (
            <table className="assets-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>RPM</th>
                  <th>Bearing</th>
                  <th>Baseline</th>
                  <th>Last Updated</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {assets.map((asset) => (
                  <tr key={asset.id}>
                    <td>{asset.name}</td>
                    <td>{asset.rpm.toLocaleString()}</td>
                    <td>{asset.bearing_type}</td>
                    <td>
                      {asset.baseline?.anomaly_index != null ? (
                        <>
                          <span className="baseline-index">
                            {(asset.baseline.anomaly_index as number).toFixed(2)}
                          </span>
                          {asset.baseline.trend_points && (asset.baseline.trend_points as unknown[]).length > 0 && (
                            <span className="trend-count">
                              ({(asset.baseline.trend_points as unknown[]).length} pts)
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="no-baseline">No baseline</span>
                      )}
                    </td>
                    <td>{new Date(asset.updated_at).toLocaleDateString()}</td>
                    <td>
                      <button
                        className="btn btn-danger btn-sm"
                        onClick={() => handleDeleteAsset(asset.id)}
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

export default OrganizationPage;