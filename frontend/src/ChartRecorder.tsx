import type { Reading } from "./api";

/* A multi-pen strip chart. The paper is pre-printed: grid, ISO 10816-3 zone
   bands and the two alarm limits exist before any data arrives, exactly as
   they do on a real chart roll. The pens then draw across it. */

const W = 1000;
const H = 320;
const M = { top: 14, right: 64, bottom: 30, left: 48 };
const PLOT = {
  x: M.left,
  y: M.top,
  w: W - M.left - M.right,
  h: H - M.top - M.bottom,
};

/* Each pen carries its own engineering range, and all three share the chart's
   0 to 100 percent grid. This is how a real multi-channel recorder works. */
const PENS = [
  { key: "vibration_mm_s", label: "Vibration", unit: "mm/s", min: 0, max: 8, color: "var(--pen-vib)" },
  { key: "temperature_c", label: "Temperature", unit: "°C", min: 20, max: 100, color: "var(--pen-temp)" },
  { key: "pressure_bar", label: "Pressure", unit: "bar", min: 0, max: 10, color: "var(--pen-press)" },
] as const;

export const PEN_SPECS = PENS;

const VIB_MAX = 8;
const ZONE_BC = 2.8;
const ZONE_D = 4.5;

const pct = (value: number, min: number, max: number) =>
  Math.max(0, Math.min(1, (value - min) / (max - min)));

const toY = (fraction: number) => PLOT.y + PLOT.h - fraction * PLOT.h;

const toX = (index: number, count: number) =>
  count <= 1 ? PLOT.x + PLOT.w / 2 : PLOT.x + (index / (count - 1)) * PLOT.w;

/* pathLength normalisation does not reliably drive stroke-dasharray, so each
   pen measures its own trace on mount and writes the real length back. */
function measurePen(node: SVGPathElement | null) {
  if (node) node.style.setProperty("--len", String(node.getTotalLength()));
}

function clockOf(timestamp: string): string {
  const parsed = new Date(timestamp);
  if (!Number.isNaN(parsed.getTime())) {
    return `${String(parsed.getHours()).padStart(2, "0")}:${String(parsed.getMinutes()).padStart(2, "0")}`;
  }
  const match = timestamp.match(/(\d{2}:\d{2})/);
  return match ? match[1] : "";
}

function valueOf(reading: Reading, key: string): number | null {
  const raw = (reading as unknown as Record<string, number | null>)[key];
  return typeof raw === "number" && Number.isFinite(raw) ? raw : null;
}

/** Index the operator should look at: the first limit breach, else the peak. */
function eventIndex(readings: Reading[]): number | null {
  if (readings.length === 0) return null;
  const breach = readings.findIndex((r) => r.vibration_mm_s > ZONE_D);
  if (breach !== -1) return breach;
  let peak = 0;
  readings.forEach((r, i) => {
    if (r.vibration_mm_s > readings[peak].vibration_mm_s) peak = i;
  });
  return readings[peak].vibration_mm_s > ZONE_BC ? peak : null;
}

export default function ChartRecorder({
  readings,
  chartKey,
}: {
  readings: Reading[];
  chartKey: string;
}) {
  const count = readings.length;
  const loaded = count > 0;
  const event = loaded ? eventIndex(readings) : null;

  const minorCols = 50;
  const minorRows = 20;
  const tickEvery = Math.max(1, Math.ceil(count / 8));

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={
        loaded
          ? `Strip chart of ${count} sensor readings. Vibration, temperature and pressure plotted against the ISO 10816-3 zone limits.`
          : "Empty strip chart, showing the printed ISO 10816-3 zone limits and no data."
      }
    >
      <rect x={0} y={0} width={W} height={H} fill="var(--paper)" />

      {/* --- printed grid --- */}
      <g aria-hidden="true">
        {Array.from({ length: minorCols + 1 }, (_, i) => {
          const x = PLOT.x + (i / minorCols) * PLOT.w;
          const major = i % 10 === 0;
          return (
            <line
              key={`c${i}`}
              x1={x} y1={PLOT.y} x2={x} y2={PLOT.y + PLOT.h}
              stroke={major ? "var(--grid-major)" : "var(--grid-minor)"}
              strokeWidth={major ? 1 : 0.5}
            />
          );
        })}
        {Array.from({ length: minorRows + 1 }, (_, i) => {
          const y = PLOT.y + (i / minorRows) * PLOT.h;
          const major = i % 4 === 0;
          return (
            <line
              key={`r${i}`}
              x1={PLOT.x} y1={y} x2={PLOT.x + PLOT.w} y2={y}
              stroke={major ? "var(--grid-major)" : "var(--grid-minor)"}
              strokeWidth={major ? 1 : 0.5}
            />
          );
        })}
      </g>

      {/* --- left scale, percent of each pen's own span --- */}
      <g fontFamily="var(--furniture)" fontSize={10} fill="var(--ink-soft)" aria-hidden="true">
        {[0, 20, 40, 60, 80, 100].map((p) => (
          <text key={p} x={PLOT.x - 8} y={toY(p / 100) + 3.5} textAnchor="end" letterSpacing="0.06em">
            {p}
          </text>
        ))}
        <text
          x={-(PLOT.y + PLOT.h / 2)} y={13}
          transform="rotate(-90)" textAnchor="middle"
          fontSize={9} letterSpacing="0.16em" fontWeight={700}
        >
          % OF SPAN
        </text>
      </g>

      {/* --- ISO 10816-3 zone bands in the right margin --- */}
      <g aria-hidden="true">
        {[
          { from: 0, to: ZONE_BC / VIB_MAX, label: "A/B", color: "var(--zone-ab)" },
          { from: ZONE_BC / VIB_MAX, to: ZONE_D / VIB_MAX, label: "C", color: "var(--zone-c)" },
          { from: ZONE_D / VIB_MAX, to: 1, label: "D", color: "var(--zone-d)" },
        ].map((zone) => {
          const top = toY(zone.to);
          const height = toY(zone.from) - top;
          return (
            <g key={zone.label}>
              <rect
                x={PLOT.x + PLOT.w + 9} y={top} width={13} height={height}
                fill={zone.color} opacity={0.17}
              />
              <rect
                x={PLOT.x + PLOT.w + 9} y={top} width={13} height={height}
                fill="none" stroke={zone.color} strokeWidth={0.75} opacity={0.65}
              />
              <text
                x={PLOT.x + PLOT.w + 27} y={top + height / 2 + 3.5}
                fontFamily="var(--furniture)" fontSize={10} fontWeight={700}
                letterSpacing="0.08em" fill={zone.color}
              >
                {zone.label}
              </text>
            </g>
          );
        })}
      </g>

      {/* --- pre-printed alarm limits --- */}
      <g aria-hidden="true">
        {[
          { value: ZONE_BC, dash: "5 4", weight: 1 },
          { value: ZONE_D, dash: "none", weight: 1.5 },
        ].map((limit) => {
          const y = toY(limit.value / VIB_MAX);
          return (
            <g key={limit.value}>
              <line
                x1={PLOT.x} y1={y} x2={PLOT.x + PLOT.w} y2={y}
                stroke="var(--pen-vib)" strokeWidth={limit.weight}
                strokeDasharray={limit.dash === "none" ? undefined : limit.dash}
                opacity={0.72}
              />
              <text
                x={PLOT.x + 6} y={y - 5}
                fontFamily="var(--furniture)" fontSize={9.5} fontWeight={700}
                letterSpacing="0.1em" fill="var(--pen-vib)"
              >
                {limit.value.toFixed(1)} MM/S
              </text>
            </g>
          );
        })}
      </g>

      {/* --- the pens --- */}
      {loaded && (
        <g key={chartKey}>
          {PENS.map((pen, penIndex) => {
            const points = readings
              .map((r, i) => {
                const value = valueOf(r, pen.key);
                return value === null
                  ? null
                  : `${toX(i, count).toFixed(2)},${toY(pct(value, pen.min, pen.max)).toFixed(2)}`;
              })
              .filter((p): p is string => p !== null);
            if (points.length === 0) return null;
            return (
              <g key={pen.key}>
                <path
                  className={`trace trace-${penIndex + 1}`}
                  ref={measurePen}
                  d={`M${points.join("L")}`}
                  stroke={pen.color}
                  strokeWidth={penIndex === 0 ? 2.1 : 1.5}
                  opacity={penIndex === 0 ? 1 : 0.82}
                />
                {points.length <= 2 &&
                  points.map((p, i) => {
                    const [cx, cy] = p.split(",");
                    return <circle key={i} cx={cx} cy={cy} r={2.6} fill={pen.color} />;
                  })}
              </g>
            );
          })}
        </g>
      )}

      {/* --- event flag where the operator should look --- */}
      {loaded && event !== null && (
        <g className="flag" key={`${chartKey}-flag`}>
          <line
            x1={toX(event, count)} y1={PLOT.y}
            x2={toX(event, count)} y2={PLOT.y + PLOT.h}
            stroke="var(--ink)" strokeWidth={1} strokeDasharray="2 3" opacity={0.55}
          />
          <path
            d={`M${toX(event, count)},${PLOT.y + 1} l 46,0 l -6,9 l 6,9 l -46,0 z`}
            fill="var(--ink)"
          />
          <text
            x={toX(event, count) + 6} y={PLOT.y + 14}
            fontFamily="var(--furniture)" fontSize={9.5} fontWeight={700}
            letterSpacing="0.09em" fill="var(--paper)"
          >
            EVENT
          </text>
        </g>
      )}

      {/* --- time axis --- */}
      {loaded && (
        <g fontFamily="var(--furniture)" fontSize={9.5} fill="var(--ink-soft)" aria-hidden="true">
          {readings.map((r, i) =>
            i % tickEvery === 0 || i === count - 1 ? (
              <text
                key={i} x={toX(i, count)} y={PLOT.y + PLOT.h + 15}
                textAnchor={i === 0 ? "start" : i === count - 1 ? "end" : "middle"}
                letterSpacing="0.06em"
              >
                {clockOf(r.timestamp)}
              </text>
            ) : null,
          )}
          <text
            x={PLOT.x + PLOT.w} y={PLOT.y + PLOT.h + 26}
            textAnchor="end" fontSize={8.5} letterSpacing="0.14em" fontWeight={600}
          >
            {count} SAMPLES
          </text>
        </g>
      )}

      {!loaded && (
        <text
          x={PLOT.x + PLOT.w / 2} y={PLOT.y + PLOT.h / 2 + 4}
          textAnchor="middle" fontFamily="var(--furniture)" fontSize={13}
          fontWeight={700} letterSpacing="0.28em" fill="var(--ink-soft)"
        >
          NO CHART LOADED
        </text>
      )}

      <rect
        x={PLOT.x} y={PLOT.y} width={PLOT.w} height={PLOT.h}
        fill="none" stroke="var(--rule)" strokeWidth={1} opacity={0.55}
      />
    </svg>
  );
}
