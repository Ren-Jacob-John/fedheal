// Renders one specialist's SHAP contributions — module8-synthesis's
// `explanation_details.shap` dict, `{feature_name: contribution}` — as a
// diverging bar chart: bars grow left (pushed the prediction toward the
// OTHER class) or right (pushed toward the predicted class) from a
// center zero line. No chart library in this project (see package.json)
// and none needed for one dimension of data — plain SVG.

const HUMAN_FEATURE_NAMES = {
  age: "Age",
  resting_bp: "Resting BP",
  cholesterol: "Cholesterol",
  max_heart_rate: "Max heart rate",
  bmi: "BMI",
  glucose: "Glucose",
  num_medications: "Medications",
  prior_admissions: "Prior admissions",
};

const WIDTH = 420;
const ROW_H = 28;
const ROW_GAP = 6;
const LABEL_W = 118;
const PAD = 8;

export default function ShapChart({ contributions, predictedLabel }) {
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
        SHAP contributions toward{" "}
        <strong>{predictedLabel ?? "this prediction"}</strong> — this case only,
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
