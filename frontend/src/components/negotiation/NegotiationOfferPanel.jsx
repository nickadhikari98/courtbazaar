import React, { useState } from "react";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { CheckCircle2, HandCoins, Loader2, Ban } from "lucide-react";
import { proposeOffer, acceptOffer } from "@/lib/negotiationApi";
import { rejectHearingRequest, cancelHearingRequest } from "@/lib/hearingRequestsApi";
import { getErrorMessage, formatINR } from "@/lib/api";

/* Fee Negotiation — the offer/counter-offer/agreement action UI. Renders
   purely off the `negotiation` object the parent's single useNegotiationPoll
   owns (shared with NegotiationChat, which renders this same data as feed
   entries) and calls the parent's `onChanged` to refresh it immediately
   after an action, rather than waiting for the next poll tick.

   Business rule (founder): proposing IS that party's acceptance — only the
   other party can Accept the current offer, which locks it permanently.
   Reject/Cancel reuse the existing, unmodified hearing-level endpoints
   (targeted-reject for the advocate, cancel for the customer) — there is no
   separate "decline this offer" concept, walking away means ending the
   hearing itself. */
export default function NegotiationOfferPanel({ hearingId, negotiation, viewerUserId, viewerRole, onChanged, onHearingEnded }) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

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

  const endHearing = async () => {
    setBusy(true);
    try {
      if (viewerRole === "counsel") {
        await rejectHearingRequest(hearingId);
      } else {
        await cancelHearingRequest(hearingId);
      }
      onHearingEnded?.();
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not do that right now"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="dashboard-card border-none">
      <CardContent className="p-5">
        <div className="cb-overline text-accent mb-2">Fee Negotiation</div>

        {agreed ? (
          <div className="flex items-center gap-2 text-sm font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2.5" data-testid="negotiation-agreed-banner">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            Agreed at {formatINR(negotiation.locked_amount)} — {new Date(negotiation.locked_at).toLocaleString("en-IN")}
          </div>
        ) : (
          <>
            {currentOffer ? (
              <div className="border rounded-lg p-3 mb-3" data-testid="current-offer">
                <div className="flex items-center gap-1.5 text-2xs font-bold uppercase tracking-wide text-accent">
                  <HandCoins className="w-3.5 h-3.5" /> Current Offer
                </div>
                <div className="text-lg font-bold mt-1">{formatINR(currentOffer.amount)}</div>
                {currentOffer.note && <p className="text-sm text-muted-foreground mt-0.5">{currentOffer.note}</p>}
                <p className="text-xs text-muted-foreground mt-1">
                  {isProposer ? "Proposed by you — waiting for the other party to respond." : "Proposed by the other party."}
                </p>
                {!isProposer && (
                  <Button type="button" size="sm" className="mt-3 bg-accent hover:bg-accent/90 font-bold" disabled={busy} onClick={submitAccept} data-testid="accept-offer">
                    {busy && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />} Accept {formatINR(currentOffer.amount)}
                  </Button>
                )}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground mb-3">No offer yet — propose an amount to start negotiating.</p>
            )}

            <div className="space-y-2">
              <Label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
                {currentOffer && !isProposer ? "Counter Offer" : "Propose an Amount"}
              </Label>
              <Input type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="₹" data-testid="offer-amount-input" />
              <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional note" data-testid="offer-note-input" />
              <Button type="button" variant="outline" disabled={busy} onClick={submitOffer} data-testid="propose-offer">
                {busy && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />} {currentOffer && !isProposer ? "Send Counter Offer" : "Propose"}
              </Button>
            </div>
          </>
        )}

        {/* Once agreed, the hearing is commercially locked — walking away via
            the pre-negotiation cancel/reject action is no longer available
            (backend refuses it too; see hearings.set_negotiated_fee). Payment
            is the only forward action from here. */}
        {!agreed && (
          <div className="mt-4 pt-3 border-t">
            <Button type="button" variant="outline" size="sm" disabled={busy} onClick={endHearing}
                    className="text-red-600 border-red-200 hover:bg-red-50 font-bold" data-testid="end-negotiation">
              <Ban className="w-3.5 h-3.5 mr-1.5" /> {viewerRole === "counsel" ? "Reject Request" : "Cancel Request"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
