// Thin fetch wrappers around the two live services this UI talks to:
//   Module 1 — auth + hospital directory + vitals upload/training-status
//   Module 7 — admin/platform: overview, rounds, flags, hospital status
//
// No React here on purpose — this file has no opinions about UI state,
// it just knows the API contracts documented in each module's README.

export const AUTH_API_BASE =
  import.meta.env.VITE_AUTH_API_BASE || "http://localhost:8001";
export const ADMIN_API_BASE =
  import.meta.env.VITE_ADMIN_API_BASE || "http://localhost:8005";
export const SYNTHESIS_API_BASE =
  import.meta.env.VITE_SYNTHESIS_API_BASE || "http://localhost:8006";

export class ApiError extends Error {
  // `detail` is the server's structured error body when it sent one
  // (e.g. {status: "incomplete_data", missing_features: [...]}); `code` is
  // its machine-readable status string.
  constructor(message, status, detail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail && typeof detail === "object" ? detail : null;
    this.code = this.detail?.status ?? null;
  }
}

async function request(base, path, { method = "GET", token, body, form, file } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  let payload;
  if (file) {
    // multipart/form-data — deliberately no Content-Type here, so the
    // browser sets the boundary itself. Setting it manually is the classic
    // way to silently break a multipart upload.
    payload = file;
  } else if (form) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    payload = form;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let resp;
  try {
    resp = await fetch(`${base}${path}`, {
      method,
      headers,
      body: payload,
      // Sends the httpOnly session cookie Module 1 sets on login — this is
      // now the primary auth path for the browser dashboard (see App.jsx).
      // The Authorization header above still works too, for any caller
      // that explicitly passes a token (curl, tests, etc.).
      credentials: "include",
    });
  } catch (networkErr) {
    throw new ApiError(
      `Couldn't reach ${base}. Is the service running? (${networkErr.message})`,
      0
    );
  }

  if (!resp.ok) {
    let detail;
    try {
      detail = (await resp.json()).detail;
    } catch {
      /* body wasn't JSON — fall through to the generic message */
    }
    const message =
      typeof detail === "string"
        ? detail
        : detail?.message || `${method} ${path} failed (${resp.status})`;
    throw new ApiError(message, resp.status, detail);
  }

  if (resp.status === 204) return null;
  return resp.json();
}

// ---------- Module 1 — Auth ----------

export const authApi = {
  base: AUTH_API_BASE,

  login(email, password) {
    const form = new URLSearchParams();
    form.set("username", email);
    form.set("password", password);
    return request(AUTH_API_BASE, "/token", { method: "POST", form }).then(
      (data) => data.access_token
    );
  },

  me(token) {
    return request(AUTH_API_BASE, "/me", { token });
  },

  // The caller's own hospital's stored vitals records (Module 1). Hospital
  // scope comes from the session, never from a parameter.
  listVitals(token) {
    return request(AUTH_API_BASE, "/vitals", { token });
  },

  // Clears the httpOnly session cookie server-side. No token needed — the
  // cookie itself is what authenticates this request.
  logout() {
    return request(AUTH_API_BASE, "/logout", { method: "POST" });
  },

  // Directory of federation members — requires a logged-in session (the
  // httpOnly cookie is sent by request()); anonymous callers get 401. Only
  // name/id/is_active/requires_label per hospital, which is exactly what
  // the map needs to place a node for every hospital in the federation.
  hospitals() {
    return request(AUTH_API_BASE, "/hospitals");
  },

  // super_admin gets { [hospitalId]: status }; anyone else gets one status
  // object for their own hospital.
  trainingStatus(token) {
    return request(AUTH_API_BASE, "/training-status", { token });
  },

  uploadVitals(token, records) {
    return request(AUTH_API_BASE, "/vitals/upload", {
      method: "POST",
      token,
      body: { records },
    });
  },

  // CSV variant — a hospital's own EHR/spreadsheet export, not hand-typed
  // JSON. `csvFile` is a browser File object from an <input type="file">.
  uploadVitalsCsv(token, csvFile) {
    const form = new FormData();
    form.append("file", csvFile);
    return request(AUTH_API_BASE, "/vitals/upload/csv", { method: "POST", token, file: form });
  },

  // This hospital's own records currently sitting in "flagged" (soft
  // outlier) status, waiting for a human to approve or reject them —
  // see review() below.
  flaggedVitals(token) {
    return request(AUTH_API_BASE, "/vitals/flagged", { token });
  },

  reviewFlaggedVitals(token, recordId, decision) {
    return request(AUTH_API_BASE, `/vitals/${recordId}/review`, {
      method: "POST",
      token,
      body: { decision },
    });
  },

  // ---- Doctor management (hospital_admin only; hospital comes from the session) ----
  listDoctors(token) {
    return request(AUTH_API_BASE, "/hospital/doctors", { token });
  },
  createDoctor(token, body) {
    return request(AUTH_API_BASE, "/hospital/doctors", { method: "POST", token, body });
  },
  setDoctorActive(token, doctorId, isActive) {
    return request(AUTH_API_BASE, `/hospital/doctors/${doctorId}`, {
      method: "PATCH", token, body: { is_active: isActive },
    });
  },

  // ---- Patient cases (clinician only; hospital scoping is enforced server-side) ----
  listCases(token) {
    return request(AUTH_API_BASE, "/cases", { token });
  },
  createCase(token, body) {
    return request(AUTH_API_BASE, "/cases", { method: "POST", token, body });
  },
  getCase(token, caseId) {
    return request(AUTH_API_BASE, `/cases/${caseId}`, { token });
  },
  addCaseVitals(token, caseId, record) {
    return request(AUTH_API_BASE, `/cases/${caseId}/vitals`, { method: "POST", token, body: { record } });
  },
  getHistory(token, caseId) {
    return request(AUTH_API_BASE, `/cases/${caseId}/history`, { token });
  },
  putHistory(token, caseId, body) {
    return request(AUTH_API_BASE, `/cases/${caseId}/history`, { method: "PUT", token, body });
  },
  reviewCase(token, caseId, decision, clinicianNote) {
    return request(AUTH_API_BASE, `/cases/${caseId}/review`, {
      method: "POST", token, body: { decision, clinician_note: clinicianNote || null },
    });
  },
};

// ---------- Module 7 — Admin / Platform ----------

export const adminApi = {
  base: ADMIN_API_BASE,

  overview(token) {
    return request(ADMIN_API_BASE, "/admin/overview", { token });
  },

  rounds(token, limit = 24) {
    return request(ADMIN_API_BASE, `/admin/rounds?limit=${limit}`, { token });
  },

  flags(token, hospitalId, limit = 50) {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (hospitalId) qs.set("hospital_id", hospitalId);
    return request(ADMIN_API_BASE, `/admin/flags?${qs.toString()}`, { token });
  },

  triggerRound(token) {
    return request(ADMIN_API_BASE, "/admin/rounds/trigger", {
      method: "POST",
      token,
    });
  },

  setHospitalStatus(token, hospitalId, isActive) {
    return request(ADMIN_API_BASE, `/admin/hospitals/${hospitalId}`, {
      method: "PATCH",
      token,
      body: { is_active: isActive },
    });
  },
};

// ---------- Module 8 — Synthesis ----------
//
// Record-based: the dashboard sends only a record id. Module 8 reads the
// stored, validated record from Module 1 using the caller's own session
// (no service credential exists in the browser), maps it to model inputs,
// routes it through Module 6 and returns the result with the model's
// stub/fallback/training status and an explanation whose feature names are
// the model's real inputs. Errors carry `err.code`: incomplete_data,
// record_not_validated, unknown_condition, unsupported_input,
// specialist_unavailable, ... (see module8-synthesis.md).
export const synthesisApi = {
  base: SYNTHESIS_API_BASE,

  synthesizeRecord(token, recordId, condition = "heart_disease") {
    return request(SYNTHESIS_API_BASE, "/synthesize/record", {
      method: "POST",
      token,
      body: { record_id: recordId, condition },
    });
  },

  modelStatus(token, condition = "heart_disease") {
    return request(
      SYNTHESIS_API_BASE,
      `/models/status?condition=${encodeURIComponent(condition)}`,
      { token }
    );
  },

  // Case-level analysis: Module 8 reads the case, history and vitals as THIS user.
  analyzeCase(token, caseId) {
    return request(SYNTHESIS_API_BASE, `/cases/${caseId}/analyze`, { method: "POST", token });
  },
};
