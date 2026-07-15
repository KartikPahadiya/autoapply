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
  const [smtpPassword, setSmtpPassword] = useState("");
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
      await api.setEmail(emailInput.trim(), smtpPassword.trim() || undefined);
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
          Enter your Gmail and App Password, upload your resume. Then search jobs, tailor your resume, and send emails — all from your own Gmail address.
        </p>

        <div className="access-card">
          {/* Step 1 — Email + App Password */}
          <div className={`access-step-row ${email ? "has-done" : ""}`}>
            <div className={`access-light ${email ? "done" : ""}`} />
            <div className="access-step-body">
              <p className={`access-step-label ${email ? "done" : ""}`}>
                {email ? "Saved" : "Step 1"}
              </p>
              <h2 className="access-step-title">Your Gmail & App Password</h2>
              <p className="access-step-desc">
                We use your Gmail's App Password to send emails directly from your address. Your real password is never used.
              </p>

              {email ? (
                <p className="access-signed-in">{email}</p>
              ) : (
                <>
                  <form onSubmit={handleSaveEmail} className="access-email-form">
                    <input
                      type="email"
                      className="access-email-input"
                      placeholder="you@gmail.com"
                      value={emailInput}
                      onChange={(e) => setEmailInput(e.target.value)}
                      disabled={savingEmail || !authChecked}
                    />
                    <input
                      type="password"
                      className="access-email-input"
                      placeholder="Gmail App Password (16 chars)"
                      value={smtpPassword}
                      onChange={(e) => setSmtpPassword(e.target.value)}
                      disabled={savingEmail || !authChecked}
                    />
                    <button className="access-btn" type="submit" disabled={savingEmail || !emailInput.trim()}>
                      {savingEmail ? "Saving…" : "Save email →"}
                    </button>
                  </form>

                  <div className="access-instructions">
                    <p className="access-instructions-title">How to get your Gmail App Password:</p>
                    <ol className="access-instructions-list">
                      <li>
                        Go to{" "}
                        <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer">
                          Google Account → Security → App Passwords
                        </a>
                      </li>
                      <li>
                        Sign in if asked. Make sure <strong>2-Step Verification is ON</strong> (required for App Passwords).
                      </li>
                      <li>
                        Click <strong>"Select app"</strong> → choose <strong>"Other (Custom name)"</strong>
                      </li>
                      <li>
                        Type <strong>"Career Agent"</strong> and click <strong>"Generate"</strong>
                      </li>
                      <li>
                        Copy the <strong>16-character code</strong> (e.g., <code>abcd efgh ijkl mnop</code>) and paste it above
                      </li>
                    </ol>
                    <p className="access-instructions-note">
                      ⚠️ This is <strong>not</strong> your Gmail password. It's a separate app-specific password. Google only shows it once — copy it immediately.
                    </p>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Step 2 — Resume */}
          <div className="access-step-row">
            <div className={`access-light ${resumeUploaded ? "done" : ""}`} />
            <div className="access-step-body">
              <p className={`access-step-label ${resumeUploaded ? "done" : ""}`}>
                {resumeUploaded ? "Uploaded" : "Step 2"}
              </p>
              <h2 className="access-step-title">Resume</h2>
              <p className="access-step-desc">
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
                  : "Resume ready · Enter email to send emails"
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
