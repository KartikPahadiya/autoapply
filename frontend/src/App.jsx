import { useEffect, useState } from "react";
import AccessPanel from "./components/AccessPanel.jsx";
import Chat from "./components/Chat.jsx";
import { api } from "./api.js";
import "./App.css";

// Connecting Gmail is a *real* browser redirect to Google and back to
// /auth/google/callback on the backend (see oauth_google.py), which then
// bounces to this app with ?login=success&email=... — so this component
// has to survive a full page navigation, not just an in-memory state
// change. sessionStorage carries the "entered" flag across that round trip
// so the user doesn't have to click Enter again after coming back from
// Google. Resume status is checked from the backend (not inferred) so
// session cookie mismatches are detected immediately.
export default function App() {
  const [authChecked, setAuthChecked] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [email, setEmail] = useState(null);
  const [resumeUploaded, setResumeUploaded] = useState(false);
  const [entered, setEntered] = useState(() => sessionStorage.getItem("entered") === "true");

  useEffect(() => {
    // Clean the ?login=success&email=... params Google/the backend appended.
    const params = new URLSearchParams(window.location.search);
    if (params.has("login")) {
      window.history.replaceState({}, "", window.location.pathname);
    }

    // Check auth + resume status from the backend (source of truth).
    Promise.allSettled([api.me(), api.resumeStatus()])
      .then(([meResult, resumeResult]) => {
        if (meResult.status === "fulfilled") {
          setLoggedIn(meResult.value.logged_in);
          setEmail(meResult.value.email);
        }
        if (resumeResult.status === "fulfilled") {
          setResumeUploaded(resumeResult.value.has_resume);
        }
      })
      .finally(() => setAuthChecked(true));
  }, []);

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
      /* best-effort — clear local state regardless */
    }
    setLoggedIn(false);
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

  const bothReady = loggedIn && resumeUploaded;

  return (
    <div className="app-shell">
      {bothReady && entered ? (
        <Chat email={email} onSignOut={handleSignOut} />
      ) : (
        <AccessPanel
          authChecked={authChecked}
          loggedIn={loggedIn}
          email={email}
          resumeUploaded={resumeUploaded}
          onResumeUploaded={handleResumeUploaded}
          onEnter={handleEnter}
        />
      )}
    </div>
  );
}
