import React, { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import LandingNav from "@/components/landing/LandingNav";
import LandingFooter from "@/components/landing/LandingFooter";
import { useAuth } from "@/context/AuthContext";
import InstantLegalHelpChat from "@/components/legalHelp/InstantLegalHelpChat";
import usePageSEO from "@/hooks/usePageSEO";

/* Dedicated, full-height Instant Legal Help page (public, no login — same
   rules as the landing-page panel it replaces; ai_chat.py decides what an
   anonymous vs signed-in visitor can see). Not wrapped in MarketingLayout:
   the chat fills the viewport below the nav (the footer sits below the fold)
   and there's no Take-a-Tour tab over the conversation.

   The landing launcher passes what the visitor typed as router state, not a
   query string, so a description of someone's legal problem never lands in
   the URL, browser history, or analytics. It's read once, then cleared from
   history so a refresh or Back→Forward doesn't send it a second time. */
export default function LegalHelp() {
  usePageSEO({
    title: "Instant Legal Help",
    description: "Describe your situation, legal issue, or court service need and get instant guidance from CourtBazaar™.",
    path: "/legal-help",
  });
  const location = useLocation();
  const navigate = useNavigate();
  const [initialMessage] = useState(() => location.state?.initialMessage || "");

  useEffect(() => {
    if (location.state?.initialMessage) navigate(location.pathname, { replace: true, state: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Signed in: a full-screen app (the sidebar carries the only logo). Guests
  // keep the site nav and footer, with the chat filling the viewport below
  // the nav (h-16 + 1px border). The chat keeps the same place in the tree in
  // both, so auth resolving after the first render never remounts it (which
  // would send the launcher's message twice).
  const fullScreen = !!useAuth()?.user;
  return (
    <div className={fullScreen ? "h-[100dvh] flex flex-col bg-background" : "min-h-screen bg-background"}>
      {!fullScreen && <LandingNav showTourTab={false} />}
      {/* A flex column, so the chat is sized by flex (not h-full, which some
          Safari versions don't resolve in a flex item) and only its message
          log scrolls. */}
      <main className={`min-h-0 flex flex-col ${fullScreen ? "flex-1" : "h-[calc(100dvh-65px)]"}`} data-testid="legal-help-main">
        <InstantLegalHelpChat initialMessage={initialMessage} fullScreen={fullScreen} />
      </main>
      {!fullScreen && <LandingFooter />}
    </div>
  );
}
