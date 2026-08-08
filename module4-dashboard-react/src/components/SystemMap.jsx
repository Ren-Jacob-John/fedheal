// A spatial reading of the whole platform, not just the hospital-facing
// slice: where each module sits, and — more importantly — exactly what
// crosses the line between two of them. Positions are in a 1000x700 space;
// cards are placed by percentage so this scales with the viewport.

const MODULES = [
  {
    id: "m1",
    n: "1",
    name: "Auth & Multi-tenancy",
    x: 220,
    y: 350,
    color: "var(--teal)",
    desc: "Issues the JWT every other module trusts to know which hospital a request belongs to — never a client-supplied field.",
  },
  {
    id: "m2",
    n: "2",
    name: "Data Validation",
    x: 220,
    y: 570,
    color: "var(--amber)",
    desc: "Five-stage gate: de-identification → schema → plausibility → cross-field consistency → outlier detection.",
  },
  {
    id: "m3",
    n: "3",
    name: "Federated Learning",
    x: 500,
    y: 620,
    color: "var(--core-halo)",
    desc: "Each hospital trains locally; only updated weights are averaged here (FedAvg) into one improved global model.",
  },
  {
    id: "m4",
    n: "4",
    name: "Hospital Dashboard",
    x: 220,
    y: 130,
    color: "var(--ink)",
    desc: "This app — where a clinician logs in, uploads vitals, and watches their hospital's status.",
  },
  {
    id: "m5",
    n: "5",
    name: "Model Zoo",
    x: 800,
    y: 200,
    color: "var(--violet)",
    desc: "One common interface over specialist models — vitals, chest X-ray, retina, skin, segmentation.",
  },
  {
    id: "m6",
    n: "6",
    name: "Condition Router",
    x: 800,
    y: 420,
    color: "var(--violet)",
    desc: "Name a disease; it pulls in every specialist model and explanation method that condition needs.",
  },
  {
    id: "m7",
    n: "7",
    name: "Admin / Platform",
    x: 500,
    y: 350,
    color: "var(--coral)",
    desc: "The operator's single view: hospital status, round-by-round accuracy, rolled-up validation flags.",
  },
];

const EDGES = [
  { from: "m4", to: "m1", label: "login → JWT" },
  { from: "m1", to: "m2", label: "vitals → 5-stage gate" },
  { from: "m1", to: "m3", label: "validated records (export)" },
  { from: "m3", to: "m7", label: "weights only — round results" },
  { from: "m2", to: "m7", label: "flag summaries, not records" },
  { from: "m1", to: "m7", label: "hospital directory (proxy)" },
  { from: "m6", to: "m5", label: "specialists + explainers" },
];

function findModule(id) {
  return MODULES.find((m) => m.id === id);
}

export default function SystemMap() {
  return (
    <div className="system-map">
      <svg className="system-map__edges" viewBox="0 0 1000 700" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
        {EDGES.map((e) => {
          const a = findModule(e.from);
          const b = findModule(e.to);
          const mx = (a.x + b.x) / 2;
          const my = (a.y + b.y) / 2;
          return (
            <g key={`${e.from}-${e.to}`}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="system-map__edge" />
              <text x={mx} y={my - 8} textAnchor="middle" className="system-map__edge-label mono">
                {e.label}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="system-map__nodes">
        {MODULES.map((m) => (
          <div
            key={m.id}
            className="system-map__node glass"
            style={{
              left: `${m.x / 10}%`,
              top: `${m.y / 7}%`,
              "--node-color": m.color,
            }}
          >
            <span className="system-map__node-n mono">{m.n}</span>
            <h3 className="system-map__node-name">{m.name}</h3>
            <p className="system-map__node-desc">{m.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
