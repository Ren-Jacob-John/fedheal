import { useCallback, useEffect, useRef, useState } from "react";
import { authApi, adminApi, ApiError } from "./api.js";
import LoginGate from "./components/LoginGate.jsx";
import TopHUD from "./components/TopHUD.jsx";
import FederationMap from "./components/FederationMap.jsx";
import RoundsRail from "./components/RoundsRail.jsx";
import DetailDrawer from "./components/DetailDrawer.jsx";
import SystemMap from "./components/SystemMap.jsx";

const POLL_MS = 12000;

export default function App() {
  // No longer persisted in localStorage — a JWT sitting there is readable
  // by any JS on the page (including an XSS payload). This is now just
  // in-memory state for the current tab; session PERSISTENCE across
  // reloads comes from the httpOnly cookie Module 1 sets on login, which
  // the bootstrap effect below checks via /me regardless of what's held
  // in memory.
  const [token, setToken] = useState(null);
  const [me, setMe] = useState(null);
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState(null);
  const [bootstrapping, setBootstrapping] = useState(true);

  const [hospitals, setHospitals] = useState([]);
  const [trainingStatus, setTrainingStatus] = useState(null);
  const [overview, setOverview] = useState(null);
  const [rounds, setRounds] = useState([]);
  const [flagsByHospital, setFlagsByHospital] = useState({});

  const [view, setView] = useState("map");
  const [selection, setSelection] = useState(null);
  const [pulseSignal, setPulseSignal] = useState(0);
  const [triggering, setTriggering] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState(null);

  const roundsRef = useRef(rounds);
  roundsRef.current = rounds;

  const loadAll = useCallback(async (tok, role, { silent = false } = {}) => {
    if (!silent) setRefreshing(true);
    try {
      const [hospitalsRes, statusRes] = await Promise.all([
        authApi.hospitals(),
        authApi.trainingStatus(tok),
      ]);
      setHospitals(hospitalsRes);
      setTrainingStatus(statusRes);

      if (role === "super_admin") {
        const [ov, rd] = await Promise.all([adminApi.overview(tok), adminApi.rounds(tok)]);
        setOverview(ov);
        setRounds(rd);
      }
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Couldn't refresh the federation.");
    } finally {
      if (!silent) setRefreshing(false);
    }
  }, []);

  // Restore a session on first load — always attempted (not gated on
  // having an in-memory token), since the real signal is the httpOnly
  // cookie, which we can't read from JS to check beforehand.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const meRes = await authApi.me();
        if (cancelled) return;
        setMe(meRes);
        await loadAll(null, meRes.role, { silent: true });
      } catch {
        if (!cancelled) setMe(null);
      } finally {
        if (!cancelled) setBootstrapping(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Background polling while a session is active.
  useEffect(() => {
    if (!me) return;
    const id = setInterval(() => loadAll(token, me.role, { silent: true }), POLL_MS);
    return () => clearInterval(id);
  }, [token, me, loadAll]);

  // Lazily fetch flags for a selected hospital (super admin only).
  useEffect(() => {
    if (!selection || selection === "core" || !me || me.role !== "super_admin") return;
    if (flagsByHospital[selection]) return;
    adminApi
      .flags(token, selection)
      .then((res) => setFlagsByHospital((prev) => ({ ...prev, [selection]: res })))
      .catch(() => setFlagsByHospital((prev) => ({ ...prev, [selection]: [] })));
  }, [selection, me, token, flagsByHospital]);

  async function handleLogin(email, password) {
    setAuthBusy(true);
    setAuthError(null);
    try {
      const tok = await authApi.login(email, password);
      // Kept in memory only (not localStorage) — the httpOnly cookie
      // Module 1 just set is what actually persists the session; this is
      // just so the current tab can pass a Bearer header if it wants to.
      setToken(tok);
      const meRes = await authApi.me(tok);
      setMe(meRes);
      await loadAll(tok, meRes.role, { silent: true });
    } catch (err) {
      setAuthError(err instanceof ApiError ? err.message : "Couldn't sign in.");
    } finally {
      setAuthBusy(false);
    }
  }

  function handleLogout() {
    authApi.logout().catch(() => {}); // clear the server-side cookie; state reset below regardless
    setToken(null);
    setMe(null);
    setHospitals([]);
    setTrainingStatus(null);
    setOverview(null);
    setRounds([]);
    setFlagsByHospital({});
    setSelection(null);
  }

  async function handleTriggerRound() {
    if (!me || me.role !== "super_admin") return;
    setTriggering(true);
    const prevLatest = roundsRef.current[0]?.round_number ?? null;
    try {
      await adminApi.triggerRound(token);
      setPulseSignal((s) => s + 1);

      let attempts = 0;
      const poll = setInterval(async () => {
        attempts += 1;
        try {
          const rd = await adminApi.rounds(token);
          setRounds(rd);
          const ov = await adminApi.overview(token);
          setOverview(ov);
          if (rd[0] && rd[0].round_number !== prevLatest) {
            setPulseSignal((s) => s + 1);
            clearInterval(poll);
            setTriggering(false);
          }
        } catch {
          /* keep polling — the round subprocess may still be starting up */
        }
        if (attempts >= 25) {
          clearInterval(poll);
          setTriggering(false);
        }
      }, 3000);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Couldn't trigger a round.");
      setTriggering(false);
    }
  }

  async function handleSetHospitalActive(hospitalId, isActive) {
    try {
      await adminApi.setHospitalStatus(token, hospitalId, isActive);
      const hospitalsRes = await authApi.hospitals();
      setHospitals(hospitalsRes);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Couldn't update that hospital.");
    }
  }

  if (bootstrapping) {
    return <div className="app-boot mono">reconnecting to the federation…</div>;
  }

  if (!me) {
    return (
      <LoginGate onLogin={handleLogin} authApiBase={authApi.base} busy={authBusy} error={authError} />
    );
  }

  const normalizedHospitals = hospitals.map((h) => {
    const status =
      me.role === "super_admin" ? trainingStatus?.[h.id] : h.id === me.hospital_id ? trainingStatus : null;
    return {
      id: h.id,
      name: h.name,
      is_active: h.is_active,
      isHome: h.id === me.hospital_id,
      records: status?.records_available ?? null,
      status: status?.status ?? null,
      last_upload: status?.last_upload ?? null,
    };
  });

  const selectedHospital =
    selection && selection !== "core" ? normalizedHospitals.find((h) => h.id === selection) : null;

  return (
    <div className="app">
      <TopHUD
        me={me}
        overview={overview}
        view={view}
        onSetView={setView}
        onLogout={handleLogout}
        onRefresh={() => loadAll(token, me.role)}
        refreshing={refreshing}
      />

      {view === "map" ? (
        <>
          <FederationMap
            hospitals={normalizedHospitals}
            selectedId={selection}
            onSelect={setSelection}
            pulseSignal={pulseSignal}
            coreLabel="Global Model"
            coreSub={
              overview?.latest_round_number != null
                ? `round #${overview.latest_round_number}`
                : "awaiting first round"
            }
          />
          {me.role === "super_admin" && (
            <RoundsRail
              rounds={rounds}
              onTrigger={handleTriggerRound}
              triggering={triggering}
              canTrigger
            />
          )}
        </>
      ) : (
        <SystemMap />
      )}

      <DetailDrawer
        selection={selection}
        onClose={() => setSelection(null)}
        me={me}
        token={token}
        hospital={selectedHospital}
        overview={overview}
        rounds={rounds}
        flags={selection && selection !== "core" ? flagsByHospital[selection] : null}
        onTriggerRound={handleTriggerRound}
        triggering={triggering}
        onUploaded={() => loadAll(token, me.role, { silent: true })}
        onSetHospitalActive={handleSetHospitalActive}
      />

      {loadError && <div className="toast toast--error">{loadError}</div>}
    </div>
  );
}
