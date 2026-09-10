import React, { useState } from "react";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import { CheckCircle2, Loader2, Ban, Lock, ChevronDown } from "lucide-react";
import { proposeOffer, acceptOffer } from "@/lib/negotiationApi";
import { rejectHearingRequest, cancelHearingRequest, endNegotiation } from "@/lib/hearingRequestsApi";
import { getErrorMessage, formatINR } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/negotiationRoles";

/* Fee Negotiation — production-hardening pass (marketplace UX rewrite).
   Same underlying calls as before (proposeOffer/acceptOffer/
   rejectHearingRequest/cancelHearingRequest/endNegotiation) and the exact
   same props — this is a UI simplification, not a new negotiation model.

   The old version rendered ONE stage-driven layout shared by both roles
   (a state badge + a grid of buttons that changed meaning depending who was
   looking). That's why the counsel's screen showed customer-only exits
   ("Choose Another Counsel") in the same visual slot as their own actions,
   and why a first-time counsel had to parse "Action Required" instead of
   just being told what to do. This version branches on viewerRole FIRST —
   the counsel's card and the advocate's card are genuinely different
   experiences (see CourtBazaar's Proxy Counsel Hiring UX rewrite):
     - Counsel: a clean offer (amount + note) -> Accept / Negotiate / Reject.
       Nothing else competes for attention.
     - Advocate: on a counter, a clean comparison (their counter vs. what you
       offered, plus their message) -> Accept Counter / Reject / Send New
       Offer. Post-agreement, the actual Payment CTA lives solely in
       NegotiationNextAction.jsx — this card never duplicates it, so there is
       still only one primary action visible on the page at a time.

   Negotiation History (every offer/counter ever made) still exists, exactly
   as before — hidden by default behind a <details> disclosure instead of
   always rendered, so the common case (respond to the one current offer)
   isn't competing with a scrolling log most viewers never need. */
export default function NegotiationOfferPanel({
  hearingId, negotiation, viewerUserId, viewerRole, hearing, onChanged, onHearingEnded, onNegotiationEnded,
}) {
  const [busy, setBusy] = useState(false);
  const [offerModal, setOfferModal] = useState(null); // null | { title, submitLabel, prefillAmount }
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [endNegotiationDialogOpen, setEndNegotiationDialogOpen] = useState(false);

  if (!negotiation) {
    return (
      <Card className="dashboard-card border-none">
        <CardContent className="p-5 text-center text-sm text-muted-foreground">Loading negotiation…</CardContent>
      </Card>
    );
  }

  const sortedOffers = [...(negotiation.offers || [])].sort((a, b) => (a.created_at < b.created_at ? -1 : 1));
  const currentOffer = negotiation.offers?.find((o) => o.offer_id === negotiation.current_offer_id) || null;
  const currentIndex = currentOffer ? sortedOffers.findIndex((o) => o.offer_id === currentOffer.offer_id) : -1;
  const previousOffer = currentIndex > 0 ? sortedOffers[currentIndex - 1] : null;
  const isProposer = currentOffer?.proposed_by_user_id === viewerUserId;
  const agreed = negotiation.status === "agreed";
  const otherRoleLabel = ROLE_LABEL[viewerRole === "customer" ? "counsel" : "customer"];

  const stage = agreed ? "agreed" : currentOffer ? (isProposer ? "waiting" : "action_required") : "no_offer";

  const openOfferModal = (title, submitLabel, prefillAmount) => {
    setAmount(prefillAmount != null ? String(prefillAmount) : "");
    setNote("");
    setOfferModal({ title, submitLabel });
  };

  const submitOfferModal = async () => {
    const value = Number(amount);
    if (!value || value <= 0) {
      toast.error("Enter an amount greater than zero");
      return;
    }
    setBusy(true);
    try {
      await proposeOffer(hearingId, value, note.trim() || undefined);
      setOfferModal(null);
      await onChanged?.();
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not send that offer"));
    } finally {
      setBusy(false);
    }
  };

  const submitAccept = async () => {
    setBusy(true);
    try {
      await acceptOffer(hearingId, currentOffer.offer_id);
      toast.success(viewerRole === "customer" ? "Counter accepted — payment is now available." : "Offer accepted!");
      await onChanged?.();
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not accept this offer"));
    } finally {
      setBusy(false);
    }
  };

  // Counsel's Reject: rejectHearingRequest (targeted-reject, terminal, same
  // endpoint as before). Advocate's Reject on a counter: endNegotiation —
  // there is no separate "reject just this counter" backend action, and
  // "close this out, go pick another counsel" is exactly what declining a
  // counter means for the requester. Both go through the same lightweight
  // Yes/Cancel dialog rather than acting instantly.
  const submitReject = async () => {
    setBusy(true);
    try {
      if (viewerRole === "counsel") {
        await rejectHearingRequest(hearingId);
        onHearingEnded?.();
      } else {
        await endNegotiation(hearingId);
        onNegotiationEnded?.();
      }
      setRejectDialogOpen(false);
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not do that right now"));
    } finally {
      setBusy(false);
    }
  };

  // Distinct from submitReject's endNegotiation call in the action_required
  // branch (that IS this same function, just labeled "Reject" there since
  // it's responding to a specific counter) — this is the advocate's own
  // walk-away option for no_offer/waiting, where there's no counter to
  // reject yet. Not shown in action_required to avoid two buttons doing
  // the same thing.
  const submitEndNegotiation = async () => {
    setBusy(true);
    try {
      await endNegotiation(hearingId);
      setEndNegotiationDialogOpen(false);
      onNegotiationEnded?.();
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not end this negotiation"));
    } finally {
      setBusy(false);
    }
  };

  const submitCancel = async () => {
    setBusy(true);
    try {
      await cancelHearingRequest(hearingId);
      setCancelDialogOpen(false);
      onHearingEnded?.();
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not cancel this request"));
    } finally {
      setBusy(false);
    }
  };

  const rejectDialog = (
    <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" className="font-bold text-red-600 border-red-200 hover:bg-red-50" disabled={busy} data-testid="reject-offer">
          <Ban className="w-4 h-4 mr-1.5" /> Reject
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reject offer?</DialogTitle>
          <DialogDescription>
            {viewerRole === "counsel"
              ? "This declines the request. The Hiring Advocate will need to look elsewhere. This can't be undone."
              : "This ends the negotiation with this counsel so you can pick someone else. This can't be undone."}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setRejectDialogOpen(false)} disabled={busy}>Cancel</Button>
          <Button type="button" onClick={submitReject} disabled={busy} className="bg-red-600 hover:bg-red-700 text-white font-bold" data-testid="confirm-reject-offer">
            {busy && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />} Yes, Reject
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  const historyDisclosure = negotiation.offers?.length > 0 && (
    <details className="mt-5 pt-4 border-t group">
      <summary className="text-2xs font-bold uppercase tracking-wide text-muted-foreground cursor-pointer flex items-center gap-1.5 list-none">
        <ChevronDown className="w-3.5 h-3.5 transition-transform group-open:rotate-180" /> View Negotiation History
      </summary>
      <div className="space-y-1.5 mt-3">
        {sortedOffers.map((o, i) => {
          const isCurrent = o.offer_id === negotiation.current_offer_id && !agreed;
          const isAccepted = o.status === "accepted";
          const time = new Date(o.created_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
          return (
            <div
              key={o.offer_id}
              className={`flex items-center justify-between gap-2 text-xs rounded-lg px-3 py-2 ${
                isCurrent || isAccepted ? "bg-accent/5 border border-accent/30" : "bg-secondary/40"
              }`}
              data-testid="offer-history-row"
            >
              <div>
                <span className="font-bold">{i === 0 ? "Offer" : "Counter Offer"} {formatINR(o.amount)}</span>
                <span className="text-muted-foreground"> · {ROLE_LABEL[o.proposed_by_role] || "—"} · {time}</span>
              </div>
              {isAccepted ? (
                <span className="text-2xs font-bold uppercase text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full flex-shrink-0">Agreed</span>
              ) : isCurrent ? (
                <span className="text-2xs font-bold uppercase text-accent bg-accent/10 px-2 py-0.5 rounded-full flex-shrink-0">Current Offer</span>
              ) : (
                <span className="text-2xs font-semibold uppercase text-muted-foreground flex-shrink-0">Superseded</span>
              )}
            </div>
          );
        })}
      </div>
    </details>
  );

  const offerModalDialog = (
    <Dialog open={!!offerModal} onOpenChange={(v) => !v && setOfferModal(null)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{offerModal?.title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Amount</Label>
            <Input type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="₹" autoFocus data-testid="offer-amount-input" />
          </div>
          <div>
            <Label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Message (optional)</Label>
            <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Travel distance is higher" data-testid="offer-note-input" />
          </div>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setOfferModal(null)} disabled={busy}>Cancel</Button>
          <Button type="button" className="bg-accent hover:bg-accent/90 font-bold" disabled={busy} onClick={submitOfferModal} data-testid="submit-offer-modal">
            {busy && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />} {offerModal?.submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  // ---------------------------------------------------------------------
  // Agreed — same compact confirmation for both roles. The Payment CTA
  // lives only in NegotiationNextAction.jsx (never duplicated here), so
  // there's exactly one primary action visible on the page once agreed.
  // ---------------------------------------------------------------------
  if (agreed) {
    return (
      <Card className="border-l-4 border-l-emerald-400 shadow-md">
        <CardContent className="p-6 text-center">
          <CheckCircle2 className="w-8 h-8 mx-auto text-emerald-600 mb-2" />
          <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Fee Agreed</div>
          <div className="text-3xl font-display font-bold mt-1" data-testid="negotiation-agreed-amount">{formatINR(negotiation.locked_amount)}</div>
          <div className="flex items-center justify-center gap-1.5 text-xs font-semibold text-emerald-700 mt-2">
            <Lock className="w-3.5 h-3.5" /> Locked
          </div>
          {historyDisclosure}
        </CardContent>
      </Card>
    );
  }

  // ---------------------------------------------------------------------
  // Counsel's view — one clean offer, three actions. Never sees the
  // advocate's own exits (End Negotiation / Cancel Request) in this slot.
  // ---------------------------------------------------------------------
  if (viewerRole === "counsel") {
    return (
      <Card className="border-l-4 border-l-accent shadow-md" data-testid="counsel-offer-card">
        <CardContent className="p-6">
          <div className="cb-overline text-accent mb-3">Fee Offer</div>

          {stage === "no_offer" && (
            <>
              <p className="text-sm text-muted-foreground mb-4">Waiting for the {ROLE_LABEL.customer} to send an offer.</p>
              <Button type="button" variant="outline" className="font-bold" disabled={busy} onClick={() => openOfferModal("Propose an Amount", "Send Offer")} data-testid="propose-offer">
                Propose an Amount Instead
              </Button>
            </>
          )}

          {stage === "waiting" && (
            <div className="text-center">
              <div className="text-3xl font-display font-bold">{formatINR(currentOffer.amount)}</div>
              <p className="text-sm text-muted-foreground mt-2">Waiting for the {ROLE_LABEL.customer} to respond to your counter offer.</p>
            </div>
          )}

          {stage === "action_required" && (
            <>
              <div className="text-center mb-4">
                <div className="text-4xl font-display font-bold" data-testid="current-offer-amount">{formatINR(currentOffer.amount)}</div>
                {currentOffer.note && <p className="text-sm text-muted-foreground mt-2 italic">"{currentOffer.note}"</p>}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <Button type="button" className="font-bold bg-accent hover:bg-accent/90" disabled={busy} onClick={submitAccept} data-testid="accept-offer">
                  {busy && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />} Accept
                </Button>
                <Button
                  type="button" variant="outline" className="font-bold" disabled={busy}
                  onClick={() => openOfferModal("Negotiate Fee", "Send Counter Offer", currentOffer.amount)}
                  data-testid="negotiate-fee"
                >
                  Negotiate Fee
                </Button>
                {rejectDialog}
              </div>
            </>
          )}

          {historyDisclosure}
          {offerModalDialog}
        </CardContent>
      </Card>
    );
  }

  // ---------------------------------------------------------------------
  // Advocate's view — no_offer/waiting are plain status text (nothing to
  // decide yet); a counter is a clean comparison against what they
  // originally offered, exactly the "Proxy Counsel proposed / Originally
  // Offered / Message" summary from the hiring-flow UX rewrite.
  // ---------------------------------------------------------------------
  return (
    <Card className="border-l-4 border-l-accent shadow-md" data-testid="advocate-offer-card">
      <CardContent className="p-6">
        <div className="cb-overline text-accent mb-3">Fee Negotiation</div>

        {stage === "no_offer" && (
          <Button type="button" variant="outline" className="w-full font-bold" disabled={busy} onClick={() => openOfferModal("Propose an Amount", "Send Offer")} data-testid="propose-offer">
            Propose an Amount
          </Button>
        )}

        {stage === "waiting" && (
          <div className="text-center">
            <div className="text-3xl font-display font-bold">{formatINR(currentOffer.amount)}</div>
            <p className="text-sm text-muted-foreground mt-2">Waiting for Counsel Response</p>
          </div>
        )}

        {stage === "action_required" && (
          <>
            <div className="text-center mb-4">
              <div className="text-2xs font-bold uppercase tracking-wide text-muted-foreground">{otherRoleLabel} proposed</div>
              <div className="text-4xl font-display font-bold mt-1" data-testid="current-offer-amount">{formatINR(currentOffer.amount)}</div>
              {previousOffer && (
                <div className="text-sm text-muted-foreground mt-1">
                  Originally offered: <span className="line-through">{formatINR(previousOffer.amount)}</span>
                </div>
              )}
              {currentOffer.note && <p className="text-sm text-muted-foreground mt-2 italic">"{currentOffer.note}"</p>}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <Button type="button" className="font-bold bg-accent hover:bg-accent/90" disabled={busy} onClick={submitAccept} data-testid="accept-offer">
                {busy && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />} Accept Counter
              </Button>
              <Button
                type="button" variant="outline" className="font-bold" disabled={busy}
                onClick={() => openOfferModal("Send New Offer", "Send Offer", hearing?.fee)}
                data-testid="send-new-offer"
              >
                Send New Offer
              </Button>
              {rejectDialog}
            </div>
          </>
        )}

        {/* Other Actions — walking away, de-emphasized below the primary
            card. "End Negotiation" only appears for no_offer/waiting: once a
            counter exists (action_required), "Reject" above already ends
            the negotiation with this counsel — a second button for the same
            outcome would just be noise. Cancel Hearing Request (destructive,
            confirmed) is always available as the one true "start over"
            escape hatch, whatever stage this is at. */}
        {stage !== "no_offer" && (
          <div className="mt-5 pt-3 border-t flex flex-wrap gap-2">
            {stage === "waiting" && (
              <Dialog open={endNegotiationDialogOpen} onOpenChange={setEndNegotiationDialogOpen}>
                <DialogTrigger asChild>
                  <Button type="button" variant="ghost" size="sm" disabled={busy} className="font-semibold" data-testid="end-negotiation">
                    End Negotiation — Choose Another Counsel
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>End negotiation with this counsel?</DialogTitle>
                    <DialogDescription>
                      This closes the request with this counsel so you can pick someone else. This can't be undone.
                    </DialogDescription>
                  </DialogHeader>
                  <DialogFooter>
                    <Button type="button" variant="outline" onClick={() => setEndNegotiationDialogOpen(false)} disabled={busy}>Keep Negotiating</Button>
                    <Button type="button" onClick={submitEndNegotiation} disabled={busy} className="bg-red-600 hover:bg-red-700 text-white font-bold" data-testid="confirm-end-negotiation">
                      {busy && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />} Yes, End Negotiation
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            )}
            <Dialog open={cancelDialogOpen} onOpenChange={setCancelDialogOpen}>
              <DialogTrigger asChild>
                <Button type="button" variant="ghost" size="sm" disabled={busy} className="text-red-600 hover:bg-red-50 font-semibold" data-testid="cancel-hearing">
                  <Ban className="w-3.5 h-3.5 mr-1.5" /> Cancel Hearing Request
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Cancel this hearing request?</DialogTitle>
                  <DialogDescription>
                    This permanently cancels the entire request, not just the negotiation with this counsel. This can't be undone.
                  </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <Button type="button" variant="outline" onClick={() => setCancelDialogOpen(false)} disabled={busy}>Keep Request</Button>
                  <Button type="button" onClick={submitCancel} disabled={busy} className="bg-red-600 hover:bg-red-700 text-white font-bold" data-testid="confirm-cancel-hearing">
                    {busy && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />} Yes, Cancel Request
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        )}

        {historyDisclosure}
        {offerModalDialog}
      </CardContent>
    </Card>
  );
}
