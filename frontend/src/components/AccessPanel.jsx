import { useRef, useState } from "react";
import { api } from "../api.js";
import "./AccessPanel.css";

export default function AccessPanel({
  email,
  resumeUploaded,
  onEmailSet,
  onResumeUploaded,
  onEnter,
  authChecked,
}) {
  const [uploading, setUploading] = useState(false);
  const [emailInput, setEmailInput] = useState("");
  const [savingEmail, setSavingEmail] = useState(false);
  const [error, setError] = useState(null);
  const [fileName, setFileName] = useState(null);
  const fileInput = useRef(null);

  const handleSaveEmail = async (e) => {
    e.preventDefault();
    if (!emailInput.trim() || !emailInput.includes("@")) return;
    setSavingEmail(true);
    setError(null);
    try {
      await api.setEmail(emailInput.trim());
      onEmailSet(emailInput.trim().toLowerCase());
    } catch (err) {
      setError(err.message || "Failed to save email.");
    } finally {
      setSavingEmail(false);
    }
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
        <h1 className="access-title">Get started in 2 steps</h1>
        <p className="access-sub">
          Enter your email and upload your resume. Then search jobs, tailor your resume, and send emails — all in one place.
        </p>

        <div className="access-card">
          {/* Row 1 — Email */}
          <div className="access-row">
            <div className="access-light-wrap">
              <div className={`access-light ${email ? "done" : ""}`} />
              <div className={`access-trace ${email ? "filled" : ""}`} />
            </div>
            <div className="access-row-body">
              <p className={`access-row-label ${email ? "done" : ""}`}>
                {email ? "Saved" : "Step 1"}
              </p>
              <h2 className="access-row-title">Your email</h2>
              <p className="access-row-desc">
                Used as the sender address when you send emails through the agent. No verification needed — just type it in.
              </p>
              {email ? (
                <p className="access-signed-in">{email}</p>
              ) : (
                <form onSubmit={handleSaveEmail} className="access-email-form">
                  <input
                    type="email"
                    className="access-email-input"
                    placeholder="you@example.com"
                    value={emailInput}
                    onChange={(e) => setEmailInput(e.target.value)}
                    disabled={savingEmail || !authChecked}
                  />
                  <button className="access-btn" type="submit" disabled={savingEmail || !emailInput.trim()}>
                    {savingEmail ? "Saving…" : "Save email →"}
                  </button>
                </form>
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

          <div className="access-status-bar">
            <span className="access-status-label">
              {resumeUploaded
                ? email
                  ? "Ready to go"
                  : "Resume ready · Email optional for sending"
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
