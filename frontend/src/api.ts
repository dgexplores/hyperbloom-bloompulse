/* Typed client for the BloomPulse API. No key is sent, the public demo is
   keyless by design and a browser bundle cannot hold a secret anyway. */

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
  anomaly_score: number;
  failure_probability_7d: number;
  predicted_failure_days: number | null;
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
    response = await fetch(`${BASE}${path}`, init);
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
