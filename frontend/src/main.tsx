import React, { useCallback, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import ChartRecorder, { PEN_SPECS } from "./ChartRecorder";
import ErrorBoundary from "./ErrorBoundary";
import { analyze, upload, MAX_BYTES, MAX_ROWS } from "./api";
import type { PulseResponse, Reading, Severity } from "./api";

const CORPUS_FALLBACK = "bloompulse-2026.08.31-v1";

const STAMP: Record<Severity, { color: string; word: string; sub: string }> = {
  normal:   { color: "var(--zone-ab)", word: "Normal",   sub: "Inside ISO 10816-3 Zone A/B. No action." },
  monitor:  { color: "var(--zone-c)",  word: "Monitor",  sub: "Drifting from baseline, still under every limit." },
  alert:    { color: "#D2600C",        word: "Alert",    sub: "A published limit has been crossed." },
  critical: { color: "var(--zone-d)",  word: "Critical", sub: "Shutdown threshold exceeded. Lockout applies." },
};

/* Demo series generated in the browser so the buttons work with no files on
   disk. Synthetic, and labelled as such wherever it is shown. */
function demoSeries(failing: boolean): Omit<Reading, "rpm">[] {
  const start = Date.UTC(2026, 7, 20, 8, 0, 0);
  return Array.from({ length: 30 }, (_, i) => {
    const drift = failing ? Math.max(0, (i - 14) / 15) : 0;
    const wobble = (n: number) => Math.sin(i * n) * 0.5 + Math.cos(i * (n * 1.7)) * 0.3;
    return {
      timestamp: new Date(start + i * 4 * 3600_000).toISOString(),
      equipment_id: "BRG-05-A",
      temperature_c: +(54 + wobble(1.1) * 3 + drift * 22).toFixed(1),
      vibration_mm_s: +(1.9 + wobble(0.7) * 0.35 + drift * 3.6).toFixed(2),
      pressure_bar: +(5 + wobble(1.4) * 0.12 + drift * 0.7).toFixed(2),
    };
  });
}

function App() {
  const [result, setResult] = useState<PulseResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState("");
  const [armed, setArmed] = useState(false);
  const [source, setSource] = useState("");
  const runCount = useRef(0);

  const readings = result?.readings ?? [];
  const chartKey = `${runCount.current}`;

  const run = useCallback(async (job: () => Promise<PulseResponse>, label: string) => {
    setBusy(true);
    setError(null);
    setSource(label);
    try {
      const response = await job();
      runCount.current += 1;
      setResult(response);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed.");
      setResult(null);
      setSource("");
    } finally {
      setBusy(false);
    }
  }, []);

  const takeFile = useCallback(
    (file: File) => {
      if (!/\.csv$/i.test(file.name)) {
        setError("That is not a CSV. Export the sheet as CSV and load it again.");
        return;
      }
      if (file.size > MAX_BYTES) {
        setError(
          `${file.name} is ${(file.size / 1024 / 1024).toFixed(1)}MB. The limit is ${MAX_BYTES / 1024 / 1024}MB, about ${MAX_ROWS} rows.`,
        );
        return;
      }
      setFileName(file.name);
      void run(() => upload(file, "BRG-05-A"), file.name);
    },
    [run],
  );

  const exportOrder = useCallback(() => {
    if (!result) return;
    const { anomaly, work_order, confidence, citations, corpus_version } = result;
    const lines = [
      `# Work order ${work_order.equipment_id}`,
      "",
      `Raised: ${new Date().toISOString()}`,
      `Source: ${source || "demo series"}`,
      `Corpus: ${corpus_version}`,
      "",
      "## Condition",
      "",
      `- Severity: ${anomaly.severity.toUpperCase()}`,
      `- Anomaly score: ${anomaly.anomaly_score}`,
      `- Failure probability, 7 day: ${(anomaly.failure_probability_7d * 100).toFixed(0)}%`,
      `- Predicted window: ${anomaly.predicted_failure_days ? `${anomaly.predicted_failure_days} days` : "none"}`,
      `- Driving channel: ${anomaly.contributing_feature.replace(/_/g, " ")}`,
      `- Confidence: ${confidence.score}%${confidence.abstain ? " (abstained)" : ""}`,
      `- Rationale: ${confidence.rationale}`,
      "",
      `${anomaly.explanation}`,
      "",
      "## Action",
      "",
      `- ${work_order.action}`,
      `- Parts: ${work_order.parts.join(", ") || "none"}`,
      `- Estimated downtime: ${work_order.estimated_downtime_hours}h`,
      `- Lockout required: ${work_order.safety_lockout_required ? "YES, per OSHA 1910.147" : "no"}`,
      `- Governing: ${work_order.regulation}`,
      "",
      "## Authority",
      "",
      ...citations.flatMap((c, i) => [
        `${i + 1}. **${c.title}**`,
        `   > ${c.span_text}`,
        `   ${c.locator} · ${c.deep_link} · ${c.version_hash}`,
        "",
      ]),
      `---`,
      result.disclaimer,
      "",
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    const at = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    link.download = `workorder-${work_order.equipment_id}-${anomaly.severity}-${at}.md`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, [result, source]);

  const stamp = result ? STAMP[result.anomaly.severity] : null;

  const penCard = useMemo(
    () =>
      PEN_SPECS.map((pen) => (
        <span className="pen" key={pen.key} style={{ ["--pen-color" as string]: pen.color }}>
          <b>{pen.label}</b>
          {pen.min} to {pen.max} {pen.unit}
        </span>
      )),
    [],
  );

  return (
    <div className="roll">
      <header className="header">
        <div className="header-top">
          <div>
            <h1 className="wordmark">
              Bloom<span className="pulse">Pulse</span>
            </h1>
            <p className="tagline">
              Load a sensor CSV. Every reading is charted against the limits that
              govern it, and every claim below carries the passage it came from.
            </p>
          </div>
          <dl className="plate">
            <div>
              <dt>Instrument</dt>
              <dd>Isolation Forest + ISO gates</dd>
            </div>
            <div>
              <dt>Corpus</dt>
              <dd>{result?.corpus_version ?? CORPUS_FALLBACK}</dd>
            </div>
            <div>
              <dt>Chart speed</dt>
              <dd>{result?.latency_ms != null ? `${result.latency_ms} ms` : "idle"}</dd>
            </div>
            <div>
              <dt>Tier</dt>
              <dd>Free, no key</dd>
            </div>
          </dl>
        </div>

        {error && (
          <p className="notice" role="alert">
            <span className="notice-tag">Not loaded</span>
            <span>{error}</span>
          </p>
        )}

        <div className={`intake${busy ? " working" : ""}`}>
          <label
            className={`field${armed ? " is-armed" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setArmed(true);
            }}
            onDragLeave={() => setArmed(false)}
            onDrop={(e) => {
              e.preventDefault();
              setArmed(false);
              const file = e.dataTransfer.files?.[0];
              if (file) takeFile(file);
            }}
          >
            <input
              type="file"
              accept=".csv,text/csv"
              aria-label="Sensor CSV file"
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) takeFile(file);
                e.target.value = "";
              }}
            />
            <span>
              <span className="field-label">Chart source</span>
              <span className="field-value">
                {fileName || "Drop a CSV here, or click to browse"}
              </span>
            </span>
          </label>
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => {
              setFileName("");
              void run(() => analyze(demoSeries(false), "BRG-05-A"), "healthy demo series (synthetic)");
            }}
          >
            Healthy sample
          </button>
          <button
            type="button"
            className="btn btn-run"
            disabled={busy}
            onClick={() => {
              setFileName("");
              void run(() => analyze(demoSeries(true), "BRG-05-A"), "failing demo series (synthetic)");
            }}
          >
            {busy ? "Reading" : "Failing sample"}
          </button>
        </div>
      </header>

      <section className="chart-block" aria-label="Sensor chart">
        <div className="chart-caption">
          <div className="pens">{penCard}</div>
          <span>{source ? `Chart: ${source}` : "Chart: none"}</span>
        </div>
        <div className="zone-key">
          <span className="zone-key-label">ISO 10816-3 vibration zones</span>
          {[
            { band: "A/B", limit: "under 2.8 mm/s", meaning: "Run without restriction", color: "var(--zone-ab)" },
            { band: "C", limit: "2.8 to 4.5", meaning: "Unsatisfactory, plan an inspection", color: "var(--zone-c)" },
            { band: "D", limit: "over 4.5", meaning: "Shut down, damage is likely", color: "var(--zone-d)" },
          ].map((zone) => (
            <span className="zone" key={zone.band}>
              <i style={{ ["--zone-color" as string]: zone.color }} aria-hidden="true" />
              <b>{zone.band}</b>
              <span className="zone-limit">{zone.limit}</span>
              <span className="zone-meaning">{zone.meaning}</span>
            </span>
          ))}
        </div>
        <div className="chart-frame">
          <ErrorBoundary label="The chart">
            <ChartRecorder readings={readings} chartKey={chartKey} />
          </ErrorBoundary>
        </div>
        <p className="chart-hint">
          Each pen has its own range, printed above, and all three share the same
          0 to 100 percent grid. The two red rules are on the paper before any
          data arrives. The flag marks the sample the verdict turns on.
          <span className="scroll-note"> Drag the chart sideways to see the whole run.</span>
        </p>
      </section>

      <p className="sr-only" role="status" aria-live="polite">
        {busy
          ? "Analysing the chart."
          : result
            ? `${result.anomaly.severity} verdict for ${result.anomaly.equipment_id}. ${result.anomaly.explanation_simple ?? ""} Confidence ${result.confidence.score} percent. ${result.citations.length} citation${result.citations.length === 1 ? "" : "s"}.`
            : ""}
      </p>

      {result && stamp ? (
        <div className="results">
          <section className="col-left" aria-label="Condition">
            <h2 className="section-rule">
              <span>Condition</span>
              <button
                type="button"
                className="link-btn"
                onClick={() => {
                  setResult(null);
                  setSource("");
                  setFileName("");
                  setError(null);
                }}
              >
                Clear and load another
              </button>
            </h2>

            <div className="verdict">
              <span className="stamp" style={{ ["--stamp-color" as string]: stamp.color }}>
                {stamp.word}
              </span>
              <div className="verdict-meta">
                <p className="verdict-id">
                  {result.work_order.equipment_type} · {readings.length} samples
                </p>
                <p className="verdict-sub">{stamp.sub}</p>
              </div>
            </div>

            <dl className="readout">
              <div>
                <dt>Anomaly</dt>
                <dd>
                  {(result.anomaly.anomaly_score * 100).toFixed(0)}
                  <small>%</small>
                </dd>
              </div>
              <div>
                <dt>Fails in 7d</dt>
                <dd>
                  {(result.anomaly.failure_probability_7d * 100).toFixed(0)}
                  <small>%</small>
                </dd>
              </div>
              <div>
                <dt>Window</dt>
                <dd>
                  {result.anomaly.predicted_failure_days ?? "None"}
                  {result.anomaly.predicted_failure_days != null && <small> days</small>}
                </dd>
              </div>
              <div>
                <dt>{result.anomaly.is_anomaly ? "Driver" : "Watch"}</dt>
                <dd style={{ fontSize: 16, paddingTop: 5 }}>
                  {result.anomaly.contributing_feature.replace(/_/g, " ")}
                </dd>
              </div>
            </dl>

            <p className="finding">{result.anomaly.explanation}</p>

            {result.anomaly.explanation_simple && (
              <p className="plain">
                <b>In plain words</b>
                {result.anomaly.explanation_simple}
              </p>
            )}

            <p className="confidence">
              {result.confidence.abstain && <span className="abstain">Abstained</span>}
              <span className="confidence-score">Confidence {result.confidence.score}%.</span>{" "}
              {result.confidence.rationale}
            </p>

            <section className="order" aria-label="Work order">
              <h2 className="section-rule">
                <span>Work order</span>
                <span>{result.work_order.regulation}</span>
              </h2>
              <dl>
                <div className="order-row">
                  <dt>Action</dt>
                  <dd>
                    {result.work_order.action}
                    {result.work_order.safety_lockout_required && (
                      <span className="lockout">Lockout 1910.147</span>
                    )}
                  </dd>
                </div>
                <div className="order-row">
                  <dt>Parts</dt>
                  <dd>{result.work_order.parts.join(", ") || "None required"}</dd>
                </div>
                <div className="order-row">
                  <dt>Downtime</dt>
                  <dd>
                    {result.work_order.estimated_downtime_hours
                      ? `${result.work_order.estimated_downtime_hours} hours`
                      : "None"}
                  </dd>
                </div>
              </dl>
              <button type="button" className="btn" style={{ marginTop: 16 }} onClick={exportOrder}>
                Export work order
              </button>
            </section>
          </section>

          <section className="col-right" aria-label="Authority">
            <h2 className="section-rule">
              <span>Authority</span>
              <span>{result.citations.length} cited</span>
            </h2>
            <ol>
              {result.citations.map((citation, i) => (
                <li className="cite" key={citation.id}>
                  <p className="cite-head">
                    <span className="cite-no">{i + 1}</span>
                    <span className="cite-title">{citation.title}</span>
                  </p>
                  <blockquote className="cite-span">{citation.span_text}</blockquote>
                  {citation.applies_to && (
                    <p className="cite-why">{citation.applies_to}</p>
                  )}
                  <p className="cite-foot">
                    <span>{citation.locator}</span>
                    {citation.synthetic && (
                      <span className="synthetic" title="Written for this demo, not taken from a published document">
                        Synthetic excerpt
                      </span>
                    )}
                    <span className="hash">{citation.version_hash}</span>
                    <a href={citation.deep_link} target="_blank" rel="noreferrer noopener">
                      Verify at source
                    </a>
                  </p>
                </li>
              ))}
            </ol>
          </section>
        </div>
      ) : (
        <section className="blank" aria-label="How to load a chart">
          <h2>Start here</h2>
          <p>
            The chart above is blank paper. Nothing has been analysed yet, and the
            red limit lines are already printed on it so you can see what your
            machine is about to be judged against.
          </p>
          <ol className="steps">
            <li>
              <b>1</b>
              <span>
                Press <strong>Failing sample</strong> to watch a bearing degrade,
                or <strong>Healthy sample</strong> to see a clean run. Both are
                synthetic and need no file.
              </span>
            </li>
            <li>
              <b>2</b>
              <span>
                Or drop your own CSV on the field above. Any export from a PLC or
                condition monitor with a timestamp, a temperature and a vibration
                column will work.
              </span>
            </li>
            <li>
              <b>3</b>
              <span>
                Read the verdict, then check the passage of the standard it was
                based on. Every claim links back to its source.
              </span>
            </li>
          </ol>
          <dl className="spec">
            <div>
              <dt>Required</dt>
              <dd>
                <code>timestamp</code>, <code>temperature_c</code>,{" "}
                <code>vibration_mm_s</code>
              </dd>
            </div>
            <div>
              <dt>Optional</dt>
              <dd>
                <code>equipment_id</code>, <code>pressure_bar</code>, <code>rpm</code>
              </dd>
            </div>
            <div>
              <dt>Limits</dt>
              <dd>
                {MAX_ROWS} rows, {MAX_BYTES / 1024 / 1024}MB, UTF-8
              </dd>
            </div>
            <div>
              <dt>Samples</dt>
              <dd>
                <a href="/sample_anomaly.csv" download>
                  sample_anomaly.csv
                </a>{" "}
                and{" "}
                <a href="/sample_normal.csv" download>
                  sample_normal.csv
                </a>
              </dd>
            </div>
          </dl>
        </section>
      )}

      <footer className="foot">
        <p className="disclaimer">
          {result?.disclaimer ??
            "Information only. Not a substitute for a certified inspection. Verify every citation at its source before acting."}
        </p>
        <p>
          HyperBloom Hacks 2026 · MIT ·{" "}
          <a href="https://github.com/dgexplores/hyperbloom-bloompulse">Source</a>
        </p>
      </footer>
    </div>
  );
}

const container = document.getElementById("root");
if (container) {
  createRoot(container).render(
    <React.StrictMode>
      <ErrorBoundary label="BloomPulse">
        <App />
      </ErrorBoundary>
    </React.StrictMode>,
  );
}
