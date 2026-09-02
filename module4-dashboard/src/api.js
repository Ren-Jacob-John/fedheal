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

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request(base, path, { method = "GET", token, body, form } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  let payload;
  if (form) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    payload = form;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let resp;
  try {
    resp = await fetch(`${base}${path}`, { method, headers, body: payload });
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
    throw new ApiError(detail || `${method} ${path} failed (${resp.status})`, resp.status);
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

  // Public directory — no token required. Only name/id/is_active per
  // hospital, which is exactly what the map needs to place a node for
  // every hospital in the federation without leaking anything about
  // hospitals a viewer isn't scoped to.
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
