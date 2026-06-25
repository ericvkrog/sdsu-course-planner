const BASE = import.meta.env.VITE_API_BASE_URL || "/api";

async function request(method, path, body) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) {
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export function generatePlan(params) {
  return request("POST", "/plan/generate", params);
}

export function adjustPlan(params) {
  return request("POST", "/plan/adjust", params);
}

export function getSwapOptions(params) {
  return request("POST", "/plan/swap-options", params);
}

export function swapCourse(params) {
  return request("POST", "/plan/swap", params);
}

export function getCourse(code) {
  return request("GET", `/courses/${encodeURIComponent(code)}`);
}

export function getPrereqGraph(code) {
  return request("GET", `/courses/${encodeURIComponent(code)}/prereq-graph`);
}

export function getMajors() {
  return request("GET", "/majors");
}

export function getDepartments() {
  return request("GET", "/departments");
}
