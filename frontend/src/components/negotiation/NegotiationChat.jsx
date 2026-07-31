import React, { useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Send, HandCoins, CheckCircle2, MessageCircle, Info } from "lucide-react";
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
      type: "message", at: m.created_at, key: m.message_id, text: m.text, senderUserId: m.sender_user_id,
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
    <div className={`flex ${isMine ? "justify-end" : "justify-start"}`} data-testid="feed-message">
      <div className={`max-w-[80%] rounded-lg px-3 py-1.5 text-sm ${isMine ? "bg-accent/10" : "bg-secondary"}`}>
        {entry.text}
        <div className="text-2xs text-muted-foreground mt-0.5">{time}</div>
      </div>
    </div>
  );
}

// SECONDARY to NegotiationOfferPanel by design — quieter header, no accent
// border/glow, smaller max-height feed — so the Fee Negotiation card above
// always reads as the more important surface. See NegotiationOfferPanel.jsx
// for why: commercial actions live there, never here.
export default function NegotiationChat({ hearingId, timeline, negotiationStatus, hearing }) {
  const { user } = useAuth();
  const { feed, sendMessage, sending } = useMessageFeed(hearingId, timeline, hearing);
  const [text, setText] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [feed.length]);

  const handleSend = async () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setText("");
    await sendMessage(trimmed);
  };

  return (
    <Card className="border shadow-none">
      <CardContent className="p-5">
        <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-muted-foreground mb-2">
          <MessageCircle className="w-3.5 h-3.5" /> Discussion Chat
        </div>
        {negotiationStatus === "agreed" && (
          <div className="flex items-center gap-1.5 text-2xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-1.5 mb-3">
            <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" /> Amount agreed — chat is for hearing logistics now.
          </div>
        )}
        <div className="space-y-2 max-h-72 overflow-y-auto mb-3 pr-1" data-testid="negotiation-feed">
          {!feed.length && <p className="text-sm text-muted-foreground text-center py-6">No messages yet — say hello.</p>}
          {feed.map((entry) => (
            <FeedEntry key={entry.key} entry={entry} isMine={entry.senderUserId === user?.user_id || entry.proposedByUserId === user?.user_id} />
          ))}
          <div ref={bottomRef} />
        </div>
        <div className="flex gap-2">
          <Input
            value={text} onChange={(e) => setText(e.target.value)} placeholder="Message"
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleSend(); } }}
            data-testid="negotiation-chat-input"
          />
          <Button type="button" variant="outline" onClick={handleSend} disabled={sending || !text.trim()} data-testid="negotiation-chat-send">
            <Send className="w-4 h-4" />
          </Button>
        </div>
        <div className="flex items-start gap-1.5 text-2xs text-muted-foreground mt-2.5 bg-secondary/50 rounded-lg px-2.5 py-2" data-testid="chat-negotiation-hint">
          <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
          <p>
            This chat is for discussing hearing details. <span className="font-bold text-foreground">Fee agreements made in chat are NOT official.</span> Use the Fee Negotiation panel above.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
