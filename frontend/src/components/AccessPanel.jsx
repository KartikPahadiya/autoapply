import { useRef, useState } from "react";
import { api } from "../api.js";
import "./AccessPanel.css";

export default function AccessPanel({
  loggedIn,
  email,
  resumeUploaded,
  onResumeUploaded,
  onEnter,
  authChecked,
}) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [fileName, setFileName] = useState(null);
  const fileInput = useRef(null);

  const handleConnectGmail = () => {
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
        <p className="access-eyebrow">Career Agent</p>
        <h1 className="access-title">Upload your resume to get started</h1>
        <p className="access-sub">
          Search jobs, tailor your resume, and look up company emails — no login required. Connect Gmail
          only when you want to send emails.
        </p>

        <div className="access-card">
          {/* Row 1 — Resume (REQUIRED) */}
          <div className="access-row">
            <div className="access-light-wrap">
              <div className={`access-light ${resumeUploaded ? "done" : ""}`} />
              <div className={`access-trace ${resumeUploaded ? "filled" : ""}`} />
            </div>
            <div className="access-row-body">
              <p className={`access-row-label ${resumeUploaded ? "done" : ""}`}>
                {resumeUploaded ? "Uploaded" : "Required"}
              </p>
              <h2 className="access-row-title">Resume</h2>
              <p className="access-row-desc">
                PDF or DOCX. Used to match you against job listings and tailor your resume for specific roles.
              </p>
              <button
                className={`access-btn ${resumeUploaded ? "done" : ""}`}
                onClick={handleFilePick}
                disabled={uploading}
              >
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

          {/* Row 2 — Gmail (OPTIONAL) */}
          <div className="access-row">
            <div className="access-light-wrap">
              <div className={`access-light ${loggedIn ? "done" : "optional"}`} />
            </div>
            <div className="access-row-body">
              <p className={`access-row-label ${loggedIn ? "done" : ""}`}>
                {loggedIn ? "Connected" : "Optional"}
              </p>
              <h2 className="access-row-title">Gmail access</h2>
              <p className="access-row-desc">
                Only needed if you want the agent to send emails on your behalf. You can connect later from the chat
                anytime.
              </p>
              {loggedIn ? (
                <p className="access-signed-in">{email}</p>
              ) : (
                <button className="access-btn ghost" onClick={handleConnectGmail} disabled={!authChecked}>
                  Connect Gmail →
                </button>
              )}
            </div>
          </div>

          <div className="access-status-bar">
            <span className="access-status-label">
              {resumeUploaded
                ? loggedIn
                  ? "Ready to go"
                  : "Resume ready · Gmail optional"
                : "Upload your resume to continue"}
            </span>
            <button className="access-enter-btn" disabled={!resumeUploaded} onClick={onEnter}>
              {resumeUploaded ? "Enter agent →" : "Agent locked"}
            </button>
          </div>
        </div>

        {error && <p className="access-error">{error}</p>}
      </div>
    </div>
  );
}
