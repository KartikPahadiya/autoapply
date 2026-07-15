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

export default function Chat({ email, onSignOut }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bodyRef = useRef(null);
  const textareaRef = useRef(null);

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
      setMessages((m) => [...m, { role: "agent", content: reply }]);
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

  return (
    <div className="console">
      <header className="console-header">
        <div className="console-header-left">
          <span className="console-dot" />
          <div>
            <p className="console-title">Career Agent</p>
            <p className="console-status">Signed in as {email}</p>
          </div>
        </div>
        <button className="console-signout" onClick={onSignOut}>
          Sign out
        </button>
      </header>

      <div className="console-body" ref={bodyRef}>
        {messages.length === 0 && (
          <div className="console-empty">
            <h3>Clearance confirmed. Where should we start?</h3>
            <p>
              Ask it to search jobs, look up a company's email, tailor your resume for a role, or send outreach —
              it'll always show you a preview and wait for your go-ahead before sending anything.
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
