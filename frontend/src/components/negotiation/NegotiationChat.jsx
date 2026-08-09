import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { HandCoins, CheckCircle2, Bell } from "lucide-react";
import { listHearingMessages, postHearingMessage } from "@/lib/hearingRequestsApi";
import { formatINR } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/negotiationRoles";

const POLL_INTERVAL_MS = 5000;

function offerEventToEntry(e) {
  return {
    type: "offer", at: e.at, key: `offer_${e.detail.offer_id}_${e.at}`,
    amount: e.detail.amount, note: e.detail.note,
    proposedByUserId: e.detail.proposed_by_user_id, proposedByRole: e.detail.proposed_by_role, isCounter: e.detail.is_counter,
  };
}

function agreedEventToEntry(e, hearing) {
  const acceptedByRole = hearing && e.detail.accepted_by_user_id === hearing.requesting_user_id ? "customer" : "counsel";
  return {
    type: "system", at: e.at, key: `agreed_${e.detail.offer_id}`,
    text: `Agreement reached at ${formatINR(e.detail.amount)} — accepted by ${ROLE_LABEL[acceptedByRole]}.`,
  };
}

/* Owns the message half of the feed — merges in the negotiation `timeline`
   passed down from the parent's single useNegotiationPoll (shared with
   NegotiationOfferPanel, so both read the same poll instead of two
   independent copies) rather than polling negotiation state itself.
   Transport-agnostic by construction: this hook only ever returns
   {feed, sendMessage, sending} — swapping the message poll below for SSE/
   websockets later means changing only this hook's internals, never the
   render below or how `timeline` gets passed in.

   Keeps polling messages for as long as the page is open, independent of
   negotiation status — chat stays live for operational discussion even
   after agreement (founder's rule), unlike the negotiation poll itself
   which the parent stops once agreed. */
function useMessageFeed(hearingId, timeline, hearing) {
  const [messages, setMessages] = useState([]);
  const [sending, setSending] = useState(false);
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  const fetchMessages = () => listHearingMessages(hearingId).then((data) => {
    if (mountedRef.current) setMessages(data);
  });

  useEffect(() => {
    let cancelled = false;
    let timer;
    const poll = () => {
      fetchMessages().catch(() => {}).finally(() => {
        if (!cancelled) timer = setTimeout(poll, POLL_INTERVAL_MS);
      });
    };
    poll();
    return () => { cancelled = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- poll loop is keyed on hearingId alone, restarted whenever it changes
  }, [hearingId]);

  const sendMessage = async (text) => {
    setSending(true);
    try {
      await postHearingMessage(hearingId, text);
      await fetchMessages(); // immediate refresh — don't wait for the next tick
    } finally {
      if (mountedRef.current) setSending(false);
    }
  };

  const feed = [
    ...messages.map((m) => ({
      type: "message", at: m.created_at, key: m.message_id, text: m.text,
      senderUserId: m.sender_user_id, senderName: m.sender_name,
    })),
    ...(timeline || []).filter((e) => e.event === "offer_proposed").map(offerEventToEntry),
    ...(timeline || []).filter((e) => e.event === "negotiation_agreed").map((e) => agreedEventToEntry(e, hearing)),
  ].sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));

  return { feed, sendMessage, sending };
}

// Offer/counter/agreement entries render as centered "timeline cards" —
// visually distinct from the left/right chat bubbles below them — so a
// glance down the feed tells commercial events (bold, bordered, colored)
// apart from ordinary logistics chat (plain bubbles) without reading either.
function FeedEntry({ entry, isMine }) {
  const time = new Date(entry.at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });

  if (entry.type === "system") {
    return (
      <div className="flex justify-center py-1" data-testid="feed-system">
        <div className="flex items-center gap-1.5 text-2xs font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-3 py-1">
          <CheckCircle2 className="w-3 h-3 flex-shrink-0" /> {entry.text} <span className="font-normal text-emerald-600/70">· {time}</span>
        </div>
      </div>
    );
  }

  if (entry.type === "offer") {
    const roleLabel = ROLE_LABEL[entry.proposedByRole] || (isMine ? "You" : "They");
    return (
      <div className="flex justify-center py-1" data-testid="feed-offer">
        <div className="max-w-[85%] rounded-lg border-2 border-accent/40 bg-accent/5 px-3.5 py-2.5 text-center">
          <div className="flex items-center justify-center gap-1.5 text-2xs font-bold uppercase tracking-wide text-accent">
            <HandCoins className="w-3.5 h-3.5" /> {entry.isCounter ? "Counter Offer" : "Offer"}
          </div>
          <div className="text-base font-bold mt-0.5">{formatINR(entry.amount)}</div>
          {entry.note && <div className="text-xs text-muted-foreground mt-0.5">{entry.note}</div>}
          <div className="text-2xs text-muted-foreground mt-1">{roleLabel} {entry.isCounter ? "countered" : "proposed"} · {time}</div>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex flex-col ${isMine ? "items-end" : "items-start"}`} data-testid="feed-message">
      <div className={`text-2xs font-bold text-muted-foreground mb-0.5 px-0.5 ${isMine ? "text-right" : "text-left"}`}>
        {isMine ? "You" : entry.senderName || "Participant"}
      </div>
      <div className={`max-w-[80%] rounded-lg px-3 py-1.5 text-sm ${isMine ? "bg-accent/10" : "bg-secondary"}`}>
        {entry.text}
        <div className="text-2xs text-muted-foreground mt-0.5">{time}</div>
      </div>
    </div>
  );
}

// SECONDARY, READ-ONLY activity feed. Every hearing message, offer, counter
// and agreement surfaces here as a running "Recent Activity" list so a glance
// shows what just happened — but you don't reply here. Sending messages and
// sharing documents both live in the "Assignment Discussion & Document
// Sharing" surface (HearingDetailDialog), which reads/writes this same thread;
// a duplicate send box here just posted the same message into two places,
// which read as confusing. Commercial actions live in NegotiationOfferPanel
// above.
// How many of the most-recent feed items the sidebar shows before collapsing
// the rest behind "View all" — this panel is a recent-activity glance, the
// full history lives in the Assignment Discussion & Document Sharing dialog.
const RECENT_LIMIT = 6;

export default function NegotiationChat({ hearingId, timeline, negotiationStatus, hearing, onViewAll }) {
  const { user } = useAuth();
  const { feed } = useMessageFeed(hearingId, timeline, hearing);
  const [unreadCount, setUnreadCount] = useState(0);
  const bottomRef = useRef(null);
  // Tracks which message ids we've already accounted for (toast + unread
  // badge) across polls — null on first render means "just mounted, don't
  // toast for history that already existed before this page was opened".
  const knownIdsRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [feed.length]);

  // New-activity notifications: this panel polls independently of the app's
  // global notification bell (which only reflects the backend's persisted
  // notification_events on its own cadence) — this gives an immediate toast
  // + a running unread count the moment a poll picks up the other party's
  // message, without waiting on that separate system.
  useEffect(() => {
    const messageEntries = feed.filter((e) => e.type === "message");
    const currentIds = new Set(messageEntries.map((e) => e.key));
    if (knownIdsRef.current) {
      const newFromOthers = messageEntries.filter((e) => !knownIdsRef.current.has(e.key) && e.senderUserId !== user?.user_id);
      if (newFromOthers.length) {
        setUnreadCount((n) => n + newFromOthers.length);
        newFromOthers.forEach((e) => {
          toast.message(e.senderName || "New message", { description: e.text });
        });
      }
    }
    knownIdsRef.current = currentIds;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-derive off feed identity, not user (stable for the page's lifetime)
  }, [feed]);

  const markSeen = () => setUnreadCount(0);

  // Only the most recent items render here; the count kept back tells the
  // "View all" link how many older items live in the full discussion.
  const visibleFeed = feed.slice(-RECENT_LIMIT);
  const hiddenCount = feed.length - visibleFeed.length;

  return (
    <Card className="border shadow-none" data-testid="negotiation-chat-panel">
      <CardContent className="p-5">
        <div className="flex items-center justify-between gap-1.5 mb-2">
          <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-muted-foreground">
            <Bell className="w-3.5 h-3.5" /> Recent Activity
          </div>
          {unreadCount > 0 && (
            <Badge className="bg-accent text-white border-0 text-2xs font-bold h-5 px-2" data-testid="chat-unread-badge">
              {unreadCount} new
            </Badge>
          )}
        </div>
        {negotiationStatus === "agreed" && (
          <div className="flex items-center gap-1.5 text-2xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-1.5 mb-3">
            <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" /> Amount agreed — remaining discussion is about hearing logistics.
          </div>
        )}
        <div
          className="space-y-2 max-h-72 overflow-y-auto mb-3 pr-1"
          data-testid="negotiation-feed"
          onMouseEnter={markSeen}
          onFocus={markSeen}
        >
          {!feed.length && <p className="text-sm text-muted-foreground text-center py-6">No activity yet.</p>}
          {visibleFeed.map((entry) => (
            <FeedEntry key={entry.key} entry={entry} isMine={entry.senderUserId === user?.user_id || entry.proposedByUserId === user?.user_id} />
          ))}
          <div ref={bottomRef} />
        </div>
        {onViewAll ? (
          <button
            type="button" onClick={onViewAll} data-testid="recent-activity-view-all"
            className="w-full text-2xs font-semibold text-accent hover:underline text-center"
          >
            {hiddenCount > 0
              ? `View all activity (${hiddenCount} more) — reply & share documents →`
              : "Reply & share documents in Assignment Discussion →"}
          </button>
        ) : (
          <p className="text-2xs text-muted-foreground text-center">
            Reply and share documents from <span className="font-semibold text-foreground">Assignment Discussion &amp; Document Sharing</span>.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
