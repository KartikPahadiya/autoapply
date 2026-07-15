import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api.js";
import "./Chat.css";

const SUGGESTIONS_ALL = [
  "Find product manager jobs in Austin",
  "Tailor my resume for this job description: …",
  "Look up emails for the top match",
  "Email me my last search results",
];

const SUGGESTIONS_GUEST = [
  "Find AI engineer jobs remote",
  "Tailor my resume for this job description: …",
  "Look up emails for Apple",
];

export default function Chat({ email, loggedIn, onSignOut }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bodyRef = useRef(null);
  const textareaRef = useRef(null);

  const suggestions = loggedIn ? SUGGESTIONS_ALL : SUGGESTIONS_GUEST;

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

  const handleConnectGmail = () => {
    window.location.href = api.googleLoginUrl();
  };

  return (
    <div className="console">
      <header className="console-header">
        <div className="console-header-left">
          <span className="console-dot" />
          <div>
            <p className="console-title">Career Agent</p>
            <p className="console-status">
              {loggedIn ? `Signed in as ${email}` : "Guest mode · Connect Gmail to send emails"}
            </p>
          </div>
        </div>
        <div className="console-header-right">
          {!loggedIn && (
            <button className="console-connect" onClick={handleConnectGmail}>
              Connect Gmail
            </button>
          )}
          <button className="console-signout" onClick={onSignOut}>
            {loggedIn ? "Sign out" : "Exit"}
          </button>
        </div>
      </header>

      <div className="console-body" ref={bodyRef}>
        {messages.length === 0 && (
          <div className="console-empty">
            <h3>Clearance confirmed. Where should we start?</h3>
            <p>
              Ask it to search jobs, look up a company's email, or tailor your resume for a role.
              {loggedIn
                ? " You can also send outreach emails when you're ready."
                : " Connect Gmail anytime if you want to send emails later."}
            </p>
            <div className="console-suggestions">
              {suggestions.map((s) => (
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
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
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
