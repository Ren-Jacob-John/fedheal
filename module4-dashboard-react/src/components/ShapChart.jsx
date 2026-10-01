// Renders one specialist's SHAP contributions — `{feature_name: contribution}` —
// as a diverging bar chart. The contributions are log-odds toward the
// model's POSITIVE class (high_risk), whichever class was predicted: bars
// grow right (toward the positive class) or left (away from it) from a
// center zero line. No chart library in this project (see package.json)
// and none needed for one dimension of data — plain SVG.

// Display names for Module 1's stored fields — the model's actual inputs.
const HUMAN_FEATURE_NAMES = {
  age_years: "Age (years)",
  systolic_bp: "Systolic BP",
  diastolic_bp: "Diastolic BP",
  heart_rate_bpm: "Heart rate",
  weight_kg: "Weight (kg)",
  height_cm: "Height (cm)",
  medication_count: "Medications",
  medication_mg_total: "Medication mg",
};

const WIDTH = 420;
const ROW_H = 28;
const ROW_GAP = 6;
const LABEL_W = 118;
const PAD = 8;

export default function ShapChart({ contributions, positiveLabel }) {
  const entries = Object.entries(contributions || {}).sort(
    (a, b) => Math.abs(b[1]) - Math.abs(a[1])
  );
  if (entries.length === 0) return null;

  const maxAbs = Math.max(...entries.map(([, v]) => Math.abs(v)), 1e-6);
  const trackW = WIDTH - LABEL_W - PAD * 2;
  const center = LABEL_W + trackW / 2;
  const height = entries.length * (ROW_H + ROW_GAP) - ROW_GAP + 4;

  return (
    <figure className="shap-chart">
      <figcaption className="shap-chart__caption">
        SHAP contributions toward the positive class{" "}
        <strong>({positiveLabel ?? "high_risk"})</strong> — this record only,
        not a general feature-importance ranking.
      </figcaption>
      <svg
        className="shap-chart__svg"
        viewBox={`0 0 ${WIDTH} ${height}`}
        role="img"
        aria-label="SHAP per-feature contribution chart"
      >
        <line
          x1={center}
          y1={0}
          x2={center}
          y2={height}
          className="shap-chart__zero-line"
        />
        {entries.map(([feature, value], i) => {
          const y = i * (ROW_H + ROW_GAP);
          const barW = (Math.abs(value) / maxAbs) * (trackW / 2 - 4);
          const positive = value >= 0;
          const x = positive ? center : center - barW;
          return (
            <g key={feature} transform={`translate(0, ${y})`}>
              <text
                x={LABEL_W - 10}
                y={ROW_H / 2}
                textAnchor="end"
                dominantBaseline="middle"
                className="shap-chart__label"
              >
                {HUMAN_FEATURE_NAMES[feature] ?? feature}
              </text>
              <rect
                x={x}
                y={4}
                width={Math.max(barW, 1)}
                height={ROW_H - 8}
                rx={3}
                className={
                  positive ? "shap-chart__bar shap-chart__bar--pos" : "shap-chart__bar shap-chart__bar--neg"
                }
              />
              <text
                x={positive ? x + barW + 6 : x - 6}
                y={ROW_H / 2}
                textAnchor={positive ? "start" : "end"}
                dominantBaseline="middle"
                className="shap-chart__value mono"
              >
                {value >= 0 ? "+" : ""}
                {value.toFixed(3)}
              </text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}
