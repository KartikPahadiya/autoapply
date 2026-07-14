import { useRef, useState } from "react";
import { api } from "../api.js";
import "./AccessPanel.css";

/**
 * Gate screen: nothing behind it is reachable until both requirements are
 * met — Gmail access (real Google OAuth redirect) and a resume upload.
 * Mirrors the backend's own rule (agent_service.py / main.py): tools that
 * send mail need session.google_creds, and matching/tailoring need
 * session.resume_text. This panel just makes that a visible checklist
 * instead of a silent failure deeper in the chat.
 */
export default function AccessPanel({ loggedIn, email, resumeUploaded, onResumeUploaded, onEnter, authChecked }) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [fileName, setFileName] = useState(null);
  const fileInput = useRef(null);

  const readyCount = (loggedIn ? 1 : 0) + (resumeUploaded ? 1 : 0);
  const bothReady = readyCount === 2;

  const handleConnectGmail = () => {
    // Real redirect — leaves the SPA and comes back to /auth/google/callback
    // on the backend, which then redirects to FRONTEND_POST_LOGIN_URL.
    window.location.href = api.googleLoginUrl();
  };

  const handleFilePick = () => fileInput.current?.click();

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      await api.uploadResume(file);
      setFileName(file.name);
      onResumeUploaded(file.name);
    } catch (err) {
      setError(err.message || "Upload failed.");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  return (
    <div className="access-screen">
      <div className="access-panel">
        <p className="access-eyebrow">Career Agent · Access Panel</p>
        <h1 className="access-title">Clear both checks to unlock the agent</h1>
        <p className="access-sub">
          Your agent can search jobs, tailor your resume, and send email on your behalf — so it needs Gmail
          access and a resume on file before it can do anything.
        </p>

        <div className="access-card">
          {/* Row 1 — Gmail */}
          <div className="access-row">
            <div className="access-light-wrap">
              <div className={`access-light ${loggedIn ? "done" : ""}`} />
              <div className={`access-trace ${loggedIn ? "filled" : ""}`} />
            </div>
            <div className="access-row-body">
              <p className={`access-row-label ${loggedIn ? "done" : ""}`}>{loggedIn ? "Connected" : "Step 1"}</p>
              <h2 className="access-row-title">Gmail access</h2>
              <p className="access-row-desc">
                Signs you in with Google and grants send-only access, used only when you ask the agent to email
                results or reach out to a company — never without your confirmation.
              </p>
              {loggedIn ? (
                <p className="access-signed-in">{email}</p>
              ) : (
                <button className="access-btn" onClick={handleConnectGmail} disabled={!authChecked}>
                  Connect Gmail →
                </button>
              )}
            </div>
          </div>

          {/* Row 2 — Resume */}
          <div className="access-row">
            <div className="access-light-wrap">
              <div className={`access-light ${resumeUploaded ? "done" : ""}`} />
            </div>
            <div className="access-row-body">
              <p className={`access-row-label ${resumeUploaded ? "done" : ""}`}>
                {resumeUploaded ? "Uploaded" : "Step 2"}
              </p>
              <h2 className="access-row-title">Resume</h2>
              <p className="access-row-desc">
                PDF or DOCX. Used to match you against job listings and as the base for any tailored resume the
                agent writes for a specific role.
              </p>
              <button className={`access-btn ${resumeUploaded ? "done" : ""}`} onClick={handleFilePick} disabled={uploading}>
                {uploading ? "Uploading…" : resumeUploaded ? "Replace resume" : "Upload resume →"}
              </button>
              <input
                ref={fileInput}
                type="file"
                accept=".pdf,.docx"
                className="access-file-input"
                onChange={handleFileChange}
              />
              {fileName && <p className="access-hint">{fileName}</p>}
            </div>
          </div>

          <div className="access-status-bar">
            <span className="access-status-label">
              Clearance <span className="access-status-count">{readyCount}/2</span>
            </span>
            <button className="access-enter-btn" disabled={!bothReady} onClick={onEnter}>
              {bothReady ? "Enter agent →" : "Agent locked"}
            </button>
          </div>
        </div>

        {error && <p className="access-error">{error}</p>}
      </div>
    </div>
  );
}
