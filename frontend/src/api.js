// Thin client around the FastAPI backend in main.py. Every call uses
// credentials: "include" so the httponly session cookie (set by
// get_or_create_session on the backend) is sent/stored across origins.
const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      /* body wasn't JSON */
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // ---- Auth -------------------------------------------------------
  me: () => request("/auth/me"),
  setEmail: (email, smtpPassword) => request("/auth/email", { method: "POST", body: JSON.stringify({ email, smtp_password: smtpPassword || "" }) }),
  logout: () => request("/auth/logout", { method: "POST" }),

  // ---- Resume -------------------------------------------------------
  uploadResume: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/resume/upload", { method: "POST", body: form });
  },
  resumeStatus: () => request("/resume/status"),
  tailorResume: (job_description, company = "", title = "") =>
    request("/resume/tailor", {
      method: "POST",
      body: JSON.stringify({ job_description, company, title }),
    }),
  tailoredResumeDownloadUrl: (key) => `${API_BASE}/resume/tailored/${encodeURIComponent(key)}/download`,

  // ---- Chat agent -----------------------------------------------------
  chat: (message) => request("/chat", { method: "POST", body: JSON.stringify({ message }) }),

  // ---- Jobs -----------------------------------------------------------
  searchJobs: (keywords, location = "") =>
    request("/jobs/search", { method: "POST", body: JSON.stringify({ keywords, location }) }),
  emailLookup: (company_or_position) =>
    request("/jobs/email-lookup", { method: "POST", body: JSON.stringify({ company_or_position }) }),
  emailMe: (recipient) => request("/jobs/email-me", { method: "POST", body: JSON.stringify({ recipient }) }),
  coldEmailPreview: (companies, message = "") =>
    request("/jobs/cold-email/preview", { method: "POST", body: JSON.stringify({ companies, message }) }),
  coldEmailSend: (items) => request("/jobs/cold-email/send", { method: "POST", body: JSON.stringify({ items }) }),

  // ---- Custom email -----------------------------------------------------
  sendCustomEmail: (to, subject, body, attach_resume = false) =>
    request("/email/custom/send", { method: "POST", body: JSON.stringify({ to, subject, body, attach_resume }) }),
};

export { ApiError };
