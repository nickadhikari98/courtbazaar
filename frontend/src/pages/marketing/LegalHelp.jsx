import React, { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import LandingNav from "@/components/landing/LandingNav";
import InstantLegalHelpChat from "@/components/legalHelp/InstantLegalHelpChat";
import usePageSEO from "@/hooks/usePageSEO";

/* Dedicated, full-height Instant Legal Help page (public, no login — same
   rules as the landing-page panel it replaces; ai_chat.py decides what an
   anonymous vs signed-in visitor can see). Not wrapped in MarketingLayout:
   a chat needs the whole viewport below the nav, with no footer to scroll
   past and no Take-a-Tour tab over the conversation.

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

  return (
    <div className="h-[100dvh] flex flex-col bg-background">
      <LandingNav showTourTab={false} />
      <main className="flex-1 min-h-0">
        <InstantLegalHelpChat initialMessage={initialMessage} />
      </main>
    </div>
  );
}
