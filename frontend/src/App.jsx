import { useEffect, useState } from "react";
import AccessPanel from "./components/AccessPanel.jsx";
import Chat from "./components/Chat.jsx";
import { api } from "./api.js";
import "./App.css";

export default function App() {
  const [authChecked, setAuthChecked] = useState(false);
  const [email, setEmail] = useState(null);
  const [resumeUploaded, setResumeUploaded] = useState(false);
  const [entered, setEntered] = useState(() => sessionStorage.getItem("entered") === "true");

  useEffect(() => {
    Promise.allSettled([api.me(), api.resumeStatus()])
      .then(([meResult, resumeResult]) => {
        if (meResult.status === "fulfilled") {
          setEmail(meResult.value.email);
        }
        if (resumeResult.status === "fulfilled") {
          setResumeUploaded(resumeResult.value.has_resume);
        }
      })
      .finally(() => setAuthChecked(true));
  }, []);

  const handleEmailSet = (email) => {
    setEmail(email);
  };

  const handleResumeUploaded = () => {
    setResumeUploaded(true);
  };

  const handleEnter = () => {
    setEntered(true);
    sessionStorage.setItem("entered", "true");
  };

  const handleSignOut = async () => {
    try {
      await api.logout();
    } catch {
      /* best-effort */
    }
    setEmail(null);
    setEntered(false);
    setResumeUploaded(false);
    sessionStorage.removeItem("entered");
  };

  if (!authChecked) {
    return (
      <div className="app-shell app-loading">
        <span>Checking session…</span>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Chat
        email={email}
        resumeUploaded={resumeUploaded}
        onSignOut={handleSignOut}
        onSetEmail={handleEmailSet}
        onResumeUploaded={handleResumeUploaded}
      />
    </div>
  );
}
