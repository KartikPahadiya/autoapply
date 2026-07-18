import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api.js";
import "./Chat.css";

const SUGGESTIONS = [
  "Find product manager jobs in Austin",
  "Tailor my resume for this job description: …",
  "Look up emails for the top match",
  "Email me my last search results",
];

function MarkdownLink({ href = "", children, ...props }) {
  const isExternal = /^https?:\/\//i.test(href);

  return (
    <a
      href={href}
      target={isExternal ? "_blank" : undefined}
      rel={isExternal ? "noopener noreferrer" : undefined}
      {...props}
    >
      {children}
    </a>
  );
}

export default function Chat({ email, resumeUploaded, onSignOut, onSetEmail, onResumeUploaded }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [editingEmail, setEditingEmail] = useState(false);
  const [emailInput, setEmailInput] = useState(email || "");
  const [uploading, setUploading] = useState(false);
  const [resumeError, setResumeError] = useState(null);
  const bodyRef = useRef(null);
  const textareaRef = useRef(null);
  const fileInput = useRef(null);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  const resizeTextarea = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  };

  const send = async (text) => {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    setMessages((m) => [...m, { role: "user", content: trimmed }]);
    setInput("");
    setSending(true);
    requestAnimationFrame(resizeTextarea);
    try {
      const { reply } = await api.chat(trimmed);
      const cleaned = reply
        .replace(/<br\s*\/?>/gi, "\n")
        .replace(/\n\s*\n/g, "\n\n");
      setMessages((m) => [...m, { role: "agent", content: cleaned }]);
    } catch (err) {
      setMessages((m) => [...m, { role: "error", content: err.message || "Something went wrong reaching the agent." }]);
    } finally {
      setSending(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    send(input);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  const handleSaveEmail = async (e) => {
    e.preventDefault();
    if (!emailInput.trim() || !emailInput.includes("@")) return;
    try {
      await api.setEmail(emailInput.trim());
      onSetEmail(emailInput.trim().toLowerCase());
      setEditingEmail(false);
    } catch (err) {
      alert(err.message || "Failed to save email.");
    }
  };

  const handleFilePick = () => fileInput.current?.click();

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setResumeError(null);
    setUploading(true);
    try {
      await api.uploadResume(file);
      onResumeUploaded(file.name);
    } catch (err) {
      setResumeError(err.message || "Upload failed.");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };
  return (
    <div className="console">
      <header className="console-header">
        <div className="console-header-left">
          <span className="console-dot" />
          <div>
            <p className="console-title">Career Agent</p>
            <p className="console-status">
              {email ? `Email: ${email}` : "No email set · enter one to send emails"}
            </p>
          </div>
        </div>
        <div className="console-header-right">
          {!email && (
            <button className="console-connect" onClick={() => setEditingEmail(true)}>
              Set email
            </button>
          )}
          {email && !editingEmail && (
            <button className="console-connect" onClick={() => { setEditingEmail(true); setEmailInput(email); }}>
              Edit email
            </button>
          )}
          <button className="console-signout" onClick={onSignOut}>
            Exit
          </button>
        </div>
      </header>

      {editingEmail && (
        <div className="console-email-bar">
          <form className="console-email-form" onSubmit={handleSaveEmail}>
            <input
              type="email"
              className="console-email-input"
              placeholder="you@example.com"
              value={emailInput}
              onChange={(e) => setEmailInput(e.target.value)}
              autoFocus
            />
            <button className="console-email-btn" type="submit" disabled={!emailInput.trim()}>
              Save
            </button>
            <button className="console-email-btn ghost" type="button" onClick={() => setEditingEmail(false)}>
              Cancel
            </button>
          </form>
        </div>
      )}

      <div className="console-body" ref={bodyRef}>
        {messages.length === 0 && (
          <div className="console-empty">
            <h3>Clearance confirmed. Where should we start?</h3>
            <p>
              Ask it to search jobs, look up a company's email, tailor your resume for a role, or send outreach emails.
            </p>
            <div className="console-suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="console-suggestion" onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`msg-row ${m.role}`}>
            <div className="msg-avatar">{m.role === "user" ? "YOU" : m.role === "error" ? "!" : "AI"}</div>
            <div className="msg-bubble">
              {m.role === "user" ? (
                m.content
              ) : (
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: MarkdownLink }}>
                  {m.content}
                </ReactMarkdown>
              )}
            </div>
          </div>
        ))}

        {sending && (
          <div className="msg-row agent">
            <div className="msg-avatar">AI</div>
            <div className="msg-bubble">
              <span className="msg-typing">
                <span />
                <span />
                <span />
              </span>
            </div>
          </div>
        )}
      </div>

      <div className="console-inputbar">
        <form className="console-form" onSubmit={handleSubmit}>
          <textarea
            ref={textareaRef}
            className="console-input"
            placeholder="Message your career agent…"
            rows={1}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              resizeTextarea();
            }}
            onKeyDown={handleKeyDown}
          />
          <button className="console-send" type="submit" disabled={sending || !input.trim()}>
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
