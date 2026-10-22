import { useEffect, useMemo, useRef, useState } from "react";

const CX = 500;
const CY = 470;
const BASE_RADIUS = 330;
const CORE_R = 64;

// Where a hospital's node radius sits on the "how much validated data do
// they have" scale. Deliberately compressed (sqrt-ish) so one hospital
// with 10x the records doesn't visually swallow the rest of the map.
function nodeRadius(records) {
  if (records == null) return 13;
  return Math.min(34, 15 + Math.sqrt(records) * 1.6);
}

function statusColor(node) {
  if (!node.is_active) return "var(--coral)";
  if (node.status === "ready_for_training") return "var(--teal)";
  if (node.status === "collecting_data") return "var(--amber)";
  return "var(--ink-faint)"; // status unknown to this viewer
}

function statusLabel(node) {
  if (!node.is_active) return "inactive";
  if (node.status === "ready_for_training") return "ready for training";
  if (node.status === "collecting_data") return "collecting data";
  return "private";
}

/**
 * Lays every hospital out on a ring around the shared model. Angle comes
 * from stable index order (so nodes don't jump around between refreshes);
 * radius pulls slightly inward for hospitals with more validated data —
 * the ones training the model most are drawn closest to it.
 */
function useLayout(hospitals) {
  return useMemo(() => {
    const n = Math.max(hospitals.length, 1);
    return hospitals.map((h, i) => {
      const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
      const engagement = h.records != null ? Math.min(h.records / 60, 1) : 0;
      const radius = BASE_RADIUS - engagement * 70;
      return {
        ...h,
        angle,
        x: CX + Math.cos(angle) * radius,
        y: CY + Math.sin(angle) * radius,
        r: nodeRadius(h.records),
      };
    });
  }, [hospitals]);
}

export default function FederationMap({
  hospitals,
  selectedId,
  onSelect,
  pulseSignal,
  coreLabel,
  coreSub,
}) {
  const laidOut = useLayout(hospitals);
  const [pulses, setPulses] = useState([]);
  const pulseIdRef = useRef(0);

  useEffect(() => {
    if (!pulseSignal) return;
    const id = pulseIdRef.current++;
    setPulses((p) => [...p, id]);
    const t = setTimeout(() => {
      setPulses((p) => p.filter((x) => x !== id));
    }, 1600);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pulseSignal]);

  return (
    <svg
      className="map"
      viewBox="0 0 1000 940"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Map of the FedHeal federation: hospitals in orbit around the shared model"
    >
      <defs>
        <radialGradient id="coreGradient" cx="50%" cy="45%" r="60%">
          <stop offset="0%" stopColor="var(--core)" />
          <stop offset="55%" stopColor="var(--core-halo)" />
          <stop offset="100%" stopColor="#1c5f80" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* orbit guide rings — purely spatial context */}
      <circle cx={CX} cy={CY} r={BASE_RADIUS} className="map__orbit-ring" />
      <circle cx={CX} cy={CY} r={BASE_RADIUS - 70} className="map__orbit-ring map__orbit-ring--inner" />

      {/* beams: hospital -> core, dashed + animated to read as "data flowing in" */}
      {laidOut.map((h) => (
        <line
          key={`beam-${h.id}`}
          x1={h.x}
          y1={h.y}
          x2={CX}
          y2={CY}
          className={
            "map__beam" +
            (h.is_active && h.status ? " map__beam--live" : "") +
            (!h.is_active ? " map__beam--off" : "")
          }
        />
      ))}

      {/* round pulses broadcasting back out from the core */}
      {pulses.map((id) => (
        <circle key={id} cx={CX} cy={CY} r={70} className="map__pulse-ring" />
      ))}

      {/* the shared model */}
      <g
        role="button"
        tabIndex={0}
        aria-label="Shared global model — view federation overview"
        className={"map__core" + (selectedId === "core" ? " is-selected" : "")}
        onClick={() => onSelect("core")}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect("core")}
      >
        <circle cx={CX} cy={CY} r={CORE_R + 46} fill="url(#coreGradient)" opacity="0.55" />
        <circle cx={CX} cy={CY} r={CORE_R} className="map__core-body" />
        <text x={CX} y={CY - 4} textAnchor="middle" className="map__core-label">
          {coreLabel}
        </text>
        <text x={CX} y={CY + 16} textAnchor="middle" className="map__core-sub mono">
          {coreSub}
        </text>
      </g>

      {/* hospitals */}
      {laidOut.map((h) => {
        const isSelected = selectedId === h.id;
        const labelAbove = Math.sin(h.angle) < -0.15;
        return (
          <g
            key={h.id}
            role="button"
            tabIndex={0}
            aria-label={`${h.name} — ${statusLabel(h)}`}
            className={"map__node" + (isSelected ? " is-selected" : "") + (h.isHome ? " is-home" : "")}
            onClick={() => onSelect(h.id)}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(h.id)}
          >
            {h.isHome && <circle cx={h.x} cy={h.y} r={h.r + 9} className="map__home-ring" />}
            <circle
              cx={h.x}
              cy={h.y}
              r={h.r}
              style={{ fill: statusColor(h), filter: `drop-shadow(0 0 8px ${statusColor(h)})` }}
              className="map__node-body"
            />
            <text
              x={h.x}
              y={labelAbove ? h.y - h.r - 12 : h.y + h.r + 20}
              textAnchor="middle"
              className="map__node-label"
            >
              {h.name}
            </text>
            {h.records != null && (
              <text
                x={h.x}
                y={labelAbove ? h.y - h.r - 1 : h.y + h.r + 34}
                textAnchor="middle"
                className="map__node-meta mono"
              >
                {h.records} rec
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
