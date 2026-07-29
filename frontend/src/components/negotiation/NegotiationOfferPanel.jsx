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
import {
  CheckCircle2, Loader2, Ban, RotateCcw, Inbox, Clock, Bell, Lock, ChevronDown, ChevronUp,
} from "lucide-react";
import { proposeOffer, acceptOffer } from "@/lib/negotiationApi";
import { rejectHearingRequest, cancelHearingRequest, endNegotiation } from "@/lib/hearingRequestsApi";
import { getErrorMessage, formatINR } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/negotiationRoles";

const STAGE_STYLE = {
  no_offer: { badge: "bg-sky-100 text-sky-700", border: "border-l-sky-400", icon: Inbox, label: "No Offer Yet" },
  waiting: { badge: "bg-amber-100 text-amber-700", border: "border-l-amber-400", icon: Clock, label: "Offer Sent" },
  action_required: { badge: "bg-orange-100 text-orange-700", border: "border-l-orange-400", icon: Bell, label: "Action Required" },
  agreed: { badge: "bg-emerald-100 text-emerald-700", border: "border-l-emerald-400", icon: CheckCircle2, label: "Agreement Reached" },
};

function StateBadge({ stage }) {
  const { badge, icon: Icon, label } = STAGE_STYLE[stage];
  return (
    <div className={`inline-flex items-center gap-1.5 text-2xs font-bold uppercase tracking-wide px-2.5 py-1 rounded-full ${badge}`} data-testid={`negotiation-stage-${stage}`}>
      <Icon className="w-3.5 h-3.5" /> {label}
    </div>
  );
}

/* Fee Negotiation — PRIMARY card of the Negotiation page (see
   NegotiationModule.jsx/NegotiationChat.jsx for why chat is secondary).
   Renders one of four explicit state cards (no_offer/waiting/action_required/
   agreed) instead of generic text, so a first-time user reads the state at a
   glance without needing "You/They proposed" style copy — the goal is
   "obvious even for someone using the platform for the first time" (founder
   UX ask), not new business logic: propose/accept/reject/cancel/end all call
   the exact same endpoints as before.

   Business rule (unchanged): proposing IS that party's acceptance — only the
   other party can Accept the current offer, which locks it permanently.
   Reject reuses the existing hearing-level endpoint (targeted-reject for the
   advocate). The customer side has two distinct exits — End Negotiation
   (closes out this counsel only) vs. Cancel Hearing Request (destructive,
   confirmed via dialog) — kept here but visually de-emphasized ("Other
   actions") since they're not part of the primary propose/accept flow. */
export default function NegotiationOfferPanel({
  hearingId, negotiation, viewerUserId, viewerRole, hearing, onChanged, onHearingEnded, onNegotiationEnded,
}) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [showCounterForm, setShowCounterForm] = useState(false);

  if (!negotiation) {
    return (
      <Card className="dashboard-card border-none">
        <CardContent className="p-5 text-center text-sm text-muted-foreground">Loading negotiation…</CardContent>
      </Card>
    );
  }

  const currentOffer = negotiation.offers?.find((o) => o.offer_id === negotiation.current_offer_id) || null;
  const isProposer = currentOffer?.proposed_by_user_id === viewerUserId;
  const agreed = negotiation.status === "agreed";
  const otherRoleLabel = ROLE_LABEL[viewerRole === "customer" ? "counsel" : "customer"];

  const stage = agreed ? "agreed" : currentOffer ? (isProposer ? "waiting" : "action_required") : "no_offer";

  const agreedEvent = agreed
    ? [...(negotiation.timeline || [])].reverse().find((e) => e.event === "negotiation_agreed")
    : null;
  const acceptedByLabel = agreedEvent && hearing
    ? ROLE_LABEL[agreedEvent.detail.accepted_by_user_id === hearing.requesting_user_id ? "customer" : "counsel"]
    : null;

  const submitOffer = async () => {
    const value = Number(amount);
    if (!value || value <= 0) {
      toast.error("Enter an amount greater than zero");
      return;
    }
    setBusy(true);
    try {
      await proposeOffer(hearingId, value, note.trim() || undefined);
      setAmount("");
      setNote("");
      setShowCounterForm(false);
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
      toast.success("Amount agreed — payment is now available.");
      await onChanged?.();
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not accept this offer"));
    } finally {
      setBusy(false);
    }
  };

  const submitReject = async () => {
    setBusy(true);
    try {
      await rejectHearingRequest(hearingId);
      onHearingEnded?.();
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not do that right now"));
    } finally {
      setBusy(false);
    }
  };

  // Distinct from submitCancel below: this closes out the negotiation with
  // the current counsel without cancelling the underlying request — the
  // parent (NegotiationModule.jsx) sends the requester back to counsel
  // selection with the same case details, rather than to a dead end.
  const submitEndNegotiation = async () => {
    setBusy(true);
    try {
      await endNegotiation(hearingId);
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

  const offerForm = (label, submitLabel) => (
    <div className="space-y-2">
      <Label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">{label}</Label>
      <Input type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="₹" data-testid="offer-amount-input" />
      <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional note" data-testid="offer-note-input" />
      <Button type="button" variant="outline" className="w-full font-bold" disabled={busy} onClick={submitOffer} data-testid="propose-offer">
        {busy && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />} {submitLabel}
      </Button>
    </div>
  );

  return (
    <Card className={`border-l-4 ${STAGE_STYLE[stage].border} shadow-md`}>
      <CardContent className="p-6">
        <div className="flex items-center justify-between mb-3">
          <div className="cb-overline text-accent">Fee Negotiation</div>
          <span className="text-2xs font-bold uppercase tracking-wide text-accent/70 border border-accent/30 rounded px-1.5 py-0.5">Primary</span>
        </div>

        <div className="mb-4"><StateBadge stage={stage} /></div>

        {stage === "no_offer" && (
          <div className="mb-4">
            <p className="text-sm text-muted-foreground">Start the commercial negotiation.</p>
          </div>
        )}

        {/* Current Active Offer — always the first thing rendered once an
            offer exists, before any stage-specific narrative or actions, so
            the amount/proposer is never something the viewer has to infer
            from a sentence further down. Same currentOffer the rest of this
            component already computes — no new data. */}
        {(stage === "waiting" || stage === "action_required") && (
          <div className="mb-4 rounded-lg border-2 border-accent/30 bg-accent/5 px-4 py-3 text-center" data-testid="current-offer-summary">
            <div className="text-2xs font-bold uppercase tracking-wide text-accent">Current Active Offer</div>
            <div className="text-3xl font-display font-bold mt-1">{formatINR(currentOffer.amount)}</div>
            <div className="text-xs text-muted-foreground mt-1">
              Proposed by <span className="font-semibold text-foreground">{isProposer ? "you" : otherRoleLabel}</span>
              {hearing && (
                <> · For the hearing at <span className="font-semibold text-foreground">{hearing.request_details?.common?.court_name || hearing.court_id}</span> on {hearing.hearing_date}</>
              )}
            </div>
            {currentOffer.note && <p className="text-xs text-muted-foreground mt-1.5 italic">"{currentOffer.note}"</p>}
          </div>
        )}

        {stage === "waiting" && (
          <div className="mb-4 text-center">
            <p className="text-sm text-muted-foreground">
              Waiting for the {otherRoleLabel} to either Accept or Send a Counter Offer.
            </p>
          </div>
        )}

        {stage === "action_required" && (
          <div className="mb-4">
            <div className={`grid grid-cols-1 ${viewerRole === "counsel" ? "sm:grid-cols-3" : "sm:grid-cols-2"} gap-2`}>
              <Button
                type="button" className="font-bold bg-accent hover:bg-accent/90 shadow-lg ring-2 ring-accent/40 animate-pulse"
                disabled={busy} onClick={submitAccept} data-testid="accept-offer"
              >
                {busy && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />} Accept {formatINR(currentOffer.amount)}
              </Button>
              <Button
                type="button" variant="outline" className="font-bold"
                onClick={() => setShowCounterForm((v) => !v)} data-testid="toggle-counter-offer"
              >
                {showCounterForm ? <ChevronUp className="w-3.5 h-3.5 mr-1.5" /> : <ChevronDown className="w-3.5 h-3.5 mr-1.5" />} Send Counter Offer
              </Button>
              {/* Decline Negotiation — the Proxy Counsel's third response
                  action alongside Accept/Counter, per the founder's ask.
                  Same rejectHearingRequest the "Other Actions" footer below
                  already calls (targeted-reject, terminal) — surfaced here
                  too, right next to the offer it's a response to, instead of
                  only in a de-emphasized footer the counsel might not scroll
                  to. Not shown for the customer viewer: their equivalent
                  exits (End Negotiation / Cancel Hearing Request) already
                  live in Other Actions below and aren't a response to *this*
                  specific offer the same way Reject is for the counsel. */}
              {viewerRole === "counsel" && (
                <Button type="button" variant="outline" className="font-bold text-red-600 border-red-200 hover:bg-red-50"
                        disabled={busy} onClick={submitReject} data-testid="decline-negotiation">
                  <Ban className="w-3.5 h-3.5 mr-1.5" /> Decline Negotiation
                </Button>
              )}
            </div>
            {showCounterForm && <div className="mt-3">{offerForm("Counter Offer", "Send Counter Offer")}</div>}
          </div>
        )}

        {stage === "agreed" && (
          <div className="mb-2">
            <div className="text-center py-2">
              <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Final Agreed Fee</div>
              <div className="text-3xl font-display font-bold mt-1" data-testid="negotiation-agreed-amount">{formatINR(negotiation.locked_amount)}</div>
            </div>
            <dl className="grid grid-cols-2 gap-3 text-sm border-t pt-3 mt-2">
              <div>
                <dt className="text-2xs font-bold uppercase tracking-wide text-muted-foreground">Accepted By</dt>
                <dd className="font-semibold mt-0.5">{acceptedByLabel || "—"}</dd>
              </div>
              <div>
                <dt className="text-2xs font-bold uppercase tracking-wide text-muted-foreground">Commercial Status</dt>
                <dd className="font-semibold mt-0.5 flex items-center gap-1 text-emerald-700"><Lock className="w-3.5 h-3.5" /> Locked</dd>
              </div>
            </dl>
            <p className="text-xs text-muted-foreground mt-3">Next step: proceed to payment below.</p>
          </div>
        )}

        {stage === "no_offer" && offerForm("Propose an Amount", "Propose Offer")}

        {/* Every offer this negotiation has ever seen, oldest first — the
            active one is always visibly "Current Offer", never left to be
            inferred from context. Same offers array accept_offer/propose_offer
            already maintain (status: active/superseded/accepted); no new data. */}
        {negotiation.offers?.length > 0 && (
          <div className="mt-5 pt-4 border-t">
            <div className="text-2xs font-bold uppercase tracking-wide text-muted-foreground mb-2">Negotiation History</div>
            <div className="space-y-1.5">
              {[...negotiation.offers].sort((a, b) => (a.created_at < b.created_at ? -1 : 1)).map((o, i) => {
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
          </div>
        )}

        {/* Once agreed, the hearing is commercially locked — walking away via
            the pre-negotiation end/cancel/reject actions is no longer
            available (backend refuses it too; see hearings.set_negotiated_fee). */}
        {/* stage === "action_required" already has this same action inline
            as "Decline Negotiation", right next to Accept/Counter — showing
            it again here too would be a second button doing the same thing. */}
        {!agreed && !(stage === "action_required" && viewerRole === "counsel") && (
          <div className="mt-5 pt-3 border-t">
            <div className="text-2xs font-bold uppercase tracking-wide text-muted-foreground mb-1.5">Other Actions</div>
            {viewerRole === "counsel" ? (
              <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={submitReject}
                      className="text-red-600 hover:bg-red-50 font-semibold" data-testid="reject-request">
                <Ban className="w-3.5 h-3.5 mr-1.5" /> Reject Request
              </Button>
            ) : (
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={submitEndNegotiation}
                        className="font-semibold" data-testid="end-negotiation">
                  {busy && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />}
                  <RotateCcw className="w-3.5 h-3.5 mr-1.5" /> End Negotiation — Choose Another Counsel
                </Button>

                <Dialog open={cancelDialogOpen} onOpenChange={setCancelDialogOpen}>
                  <DialogTrigger asChild>
                    <Button type="button" variant="ghost" size="sm" disabled={busy}
                            className="text-red-600 hover:bg-red-50 font-semibold" data-testid="cancel-hearing">
                      <Ban className="w-3.5 h-3.5 mr-1.5" /> Cancel Hearing Request
                    </Button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>Cancel this hearing request?</DialogTitle>
                      <DialogDescription>
                        This permanently cancels the entire request, not just the negotiation with this counsel.
                        This can't be undone.
                      </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                      <Button type="button" variant="outline" onClick={() => setCancelDialogOpen(false)} disabled={busy}>
                        Keep Request
                      </Button>
                      <Button type="button" onClick={submitCancel} disabled={busy}
                              className="bg-red-600 hover:bg-red-700 text-white font-bold" data-testid="confirm-cancel-hearing">
                        {busy && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />} Yes, Cancel Request
                      </Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
