/* Typed client for the BloomPulse API. */
export type Severity = "normal" | "monitor" | "alert" | "critical";

export interface Reading {
  timestamp: string;
  equipment_id: string;
  temperature_c: number;
  vibration_mm_s: number;
  pressure_bar: number | null;
  rpm: number | null;
}

export interface Citation {
  id: string;
  source_type: "statute" | "standard" | "manual" | "directive";
  title: string;
  span_text: string;
  deep_link: string;
  locator: string;
  version_hash: string;
  applies_to: string | null;
  synthetic: boolean;
}

export interface Anomaly {
  equipment_id: string;
  is_anomaly: boolean;
  /** 0..1 index of distance from the machine's own baseline. Not a probability. */
  anomaly_index: number;
  /** How soon to inspect. A policy lookup on severity, not a failure prediction. */
  inspection_window_days: number | null;
  contributing_feature: string;
  severity: Severity;
  explanation: string;
  explanation_simple: string | null;
}

export interface WorkOrder {
  equipment_id: string;
  equipment_type: string;
  action: string;
  parts: string[];
  estimated_downtime_hours: number;
  safety_lockout_required: boolean;
  regulation: string;
}

export interface PulseResponse {
  anomaly: Anomaly;
  readings: Reading[];
  citations: Citation[];
  confidence: { score: number; rationale: string; abstain: boolean };
  work_order: WorkOrder;
  corpus_version: string;
  disclaimer: string;
  latency_ms: number | null;
  free_tier: boolean;
}

export interface Asset {
  id: string;
  name: string;
  rpm: number;
  bearing_type: string;
  baseline: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface APIKey {
  id: string;
  name: string;
  key_hash: string;
  organization_id: string;
  scopes: string[];
  is_active: boolean;
  created_at: string;
}

const BASE =
  (import.meta.env.VITE_API_URL as string | undefined) ||
  (import.meta.env.PROD ? "" : "http://localhost:8000");

export const MAX_BYTES = 2 * 1024 * 1024;
export const MAX_ROWS = 500;

/** Pull the server's message out of a failed response, whatever shape it is. */
async function failure(response: Response): Promise<Error> {
  let detail = `Request failed with status ${response.status}.`;
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") {
      detail = body.detail;
    } else if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
      detail = body.detail.map((d: { msg: string }) => d.msg).join(". ");
    }
  } catch {
    /* A proxy or gateway error is not JSON. The status line above stands. */
  }
  return new Error(detail);
}

async function send(path: string, init: RequestInit): Promise<PulseResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      credentials: "include",
    });
  } catch {
    throw new Error(
      BASE
        ? `Could not reach the analyser at ${BASE}. Check that the API is running.`
        : "Could not reach the analyser. Check your connection and retry.",
    );
  }
  if (!response.ok) throw await failure(response);
  return (await response.json()) as PulseResponse;
}

export function analyze(readings: Omit<Reading, "rpm">[], equipmentId: string) {
  return send("/api/v1/pulse/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ equipment_id: equipmentId, readings }),
  });
}

export function upload(file: File, equipmentId: string) {
  const form = new FormData();
  form.append("file", file);
  return send(
    `/api/v1/pulse/upload?equipment_id=${encodeURIComponent(equipmentId)}`,
    { method: "POST", body: form },
  );
}

export async function fetchAssets(): Promise<Asset[]> {
  const response = await fetch(`${BASE}/api/v1/assets`, {
    credentials: "include",
  });
  if (!response.ok) throw await failure(response);
  return response.json() as Promise<Asset[]>;
}

export async function createAsset(asset: { name: string; rpm: number; bearing_type: string }): Promise<Asset> {
  const response = await fetch(`${BASE}/api/v1/assets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(asset),
  });
  if (!response.ok) throw await failure(response);
  return response.json() as Promise<Asset>;
}

export async function deleteAsset(assetId: string): Promise<void> {
  const response = await fetch(`${BASE}/api/v1/assets/${assetId}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!response.ok) throw await failure(response);
}

export async function fetchAPIKeys(): Promise<APIKey[]> {
  const response = await fetch(`${BASE}/api/v1/api-keys`, {
    credentials: "include",
  });
  if (!response.ok) throw await failure(response);
  return response.json() as Promise<APIKey[]>;
}

export async function createAPIKey(key: { name: string; scopes: string[] }): Promise<{ api_key: string; key: APIKey }> {
  const response = await fetch(`${BASE}/api/v1/api-keys`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(key),
  });
  if (!response.ok) throw await failure(response);
  return response.json() as Promise<{ api_key: string; key: APIKey }>;
}

export async function deleteAPIKey(keyId: string): Promise<void> {
  const response = await fetch(`${BASE}/api/v1/api-keys/${keyId}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!response.ok) throw await failure(response);
}