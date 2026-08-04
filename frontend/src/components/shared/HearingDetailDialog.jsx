import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { formatINR } from "@/lib/api";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Star, FileText, Send, Upload, CheckCircle2, X, Ban, Loader2, Gavel } from "lucide-react";
import {
  getHearingRequest, acceptHearingRequest, declineHearingRequest, rejectHearingRequest, cancelHearingRequest,
  markHearingConducted, rateHearingRequest, addHearingNote, listHearingMessages,
  postHearingMessage, listHearingDocuments, uploadHearingDocument, getHearingDocumentUrl,
  submitHearingCaseDetails,
} from "@/lib/hearingRequestsApi";
import { payForHearing as payForHearingShared } from "@/lib/hearingPayment";
import HearingTimeline from "@/components/shared/HearingTimeline";
import HearingProgressStepper from "@/components/shared/HearingProgressStepper";
import EscrowStagePanel from "@/components/negotiation/EscrowStagePanel";
import ProxyCounselCaseDetailsForm from "@/components/proxyCounsel/ProxyCounselCaseDetailsForm";
import { HEARING_STATUS_BADGE_COLOR, roleAwareStatusLabel, getHearingPermissions } from "@/lib/hearingLifecycle";

/* Shared between the advocate side (HireProxyCounsel.jsx) and the proxy
   counsel side (Practice.jsx's Hearings tab) — the same dialog, with
   contextual actions computed from the viewer's relationship to the hearing
   (requester vs assigned proxy counsel) and its current status. */
export default function HearingDetailDialog({ hearingId, open, onOpenChange, onChanged }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [hearing, setHearing] = useState(null);
  const [messages, setMessages] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [note, setNote] = useState("");
  const [messageText, setMessageText] = useState("");
  const [rating, setRating] = useState(5);
  const [review, setReview] = useState("");
  const [busy, setBusy] = useState(false);
  const [paying, setPaying] = useState(false);
  const [submittingDetails, setSubmittingDetails] = useState(false);
  const fileInputRef = useRef(null);

  const load = () => {
    if (!hearingId) return;
    getHearingRequest(hearingId).then(setHearing).catch(() => toast.error("Could not load this hearing"));
    listHearingMessages(hearingId).then(setMessages).catch(() => {});
    listHearingDocuments(hearingId).then(setDocuments).catch(() => {});
  };
  useEffect(() => { if (open) load(); }, [open, hearingId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!hearing) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Loading…</DialogTitle>
            <DialogDescription>Fetching this hearing request's details.</DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    );
  }

  // Production-hardening pass: every permission/state boolean this dialog
  // needs now comes from the one shared resolver (lib/hearingLifecycle.js)
  // that NegotiationModule.jsx also calls — this dialog no longer maintains
  // its own copy that could drift out of sync with the Negotiation page.
  const {
    isRequester, isAssignedProxyCounsel, isTargetedAtMe, canAccept, canDecline, canReject,
    negotiationRequired, negotiationAgreed, negotiationPending, canPay, canCancel, canMarkConducted, canRate,
    isEscrowParticipant, viewerRole,
  } = getHearingPermissions(hearing, user);

  const run = async (fn) => {
    setBusy(true);
    try {
      await fn();
      onChanged?.();
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "That didn't work");
    } finally {
      setBusy(false);
    }
  };

  const payForHearing = async () => {
    setPaying(true);
    try {
      await payForHearingShared(hearingId, hearing, user, {
        onSuccess: ({ simulated }) => {
          toast.success(simulated ? "Payment successful (simulated Razorpay) — held by CourtBazaar" : "Payment successful — held by CourtBazaar");
          onChanged?.();
          load();
        },
      });
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Payment could not be started");
    } finally {
      setPaying(false);
    }
  };

  // BlaBlaCar-style flow (founder direction): only reachable once payment
  // is confirmed — see ProxyCounselCaseDetailsForm/hearings.submit_case_details.
  const submitCaseDetails = async (fields) => {
    setSubmittingDetails(true);
    try {
      await submitHearingCaseDetails(hearingId, fields);
      toast.success("Case details shared with your counsel");
      onChanged?.();
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not share case details");
    } finally {
      setSubmittingDetails(false);
    }
  };

  const sendMessage = async () => {
    if (!messageText.trim()) return;
    await postHearingMessage(hearingId, messageText.trim());
    setMessageText("");
    listHearingMessages(hearingId).then(setMessages);
  };

  const submitNote = async () => {
    if (!note.trim()) return;
    await addHearingNote(hearingId, note.trim());
    setNote("");
    load();
  };

  const submitRating = async () => {
    await run(() => rateHearingRequest(hearingId, rating, review || undefined));
    setReview("");
  };

  const uploadFile = async (kind) => {
    const file = fileInputRef.current?.files?.[0];
    if (!file) return;
    await run(() => uploadHearingDocument(hearingId, kind, file));
    fileInputRef.current.value = "";
  };

  const openDocument = async (docId) => {
    try {
      const { url } = await getHearingDocumentUrl(hearingId, docId);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch {
      toast.error("Could not open this document");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display text-xl flex items-center gap-2">
            {hearing.court_id}
            <Badge className={`${HEARING_STATUS_BADGE_COLOR[hearing.status] || ""} border-0 font-bold uppercase text-2xs`}>
              {roleAwareStatusLabel(hearing, viewerRole)}
            </Badge>
          </DialogTitle>
          <DialogDescription>
            Hearing date {hearing.hearing_date}{hearing.fee ? ` · Fee ₹${hearing.fee}` : ""}
          </DialogDescription>
        </DialogHeader>

        <HearingProgressStepper status={hearing.status} negotiationAgreed={!negotiationRequired || negotiationAgreed} targeted={negotiationRequired} />

        {/* BlaBlaCar-style flow (founder direction): the case brief only
            exists once the requester has submitted it, which the backend
            only allows once payment_confirmed_at is set — see
            hearings.submit_case_details. Three states: already shared (show
            it), requester can share it now (show the form), or nothing to
            show yet (status line, for the counsel/other viewer). */}
        {hearing.details_submitted ? (
          <div className="text-sm border rounded-lg p-3 bg-secondary/30">{hearing.case_details}</div>
        ) : isRequester && hearing.payment_confirmed_at ? (
          <ProxyCounselCaseDetailsForm onSubmit={submitCaseDetails} submitting={submittingDetails} />
        ) : (
          <div className="text-sm border rounded-lg p-3 bg-secondary/30 text-muted-foreground italic">
            {hearing.payment_confirmed_at ? "Waiting for the client to share case details." : "Case details will be shared once payment is confirmed."}
          </div>
        )}

        {canPay && (
          <div className="border rounded-lg p-4 bg-accent/5 border-accent/30 space-y-2">
            <div className="font-display font-bold text-sm">Complete payment to proceed</div>
            <p className="text-xs text-muted-foreground">
              Your payment of {formatINR(hearing.fee)} will be held securely by CourtBazaar and released to the advocate
              only after the hearing is verified.
            </p>
            <Button type="button" onClick={payForHearing} disabled={paying} className="bg-accent hover:bg-accent/90 font-bold">
              {paying ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : null} Pay {formatINR(hearing.fee)}
            </Button>
          </div>
        )}

        {negotiationPending && (
          <div className="border rounded-lg p-4 bg-amber-50 border-amber-200 space-y-2">
            <div className="font-display font-bold text-sm">Fee negotiation isn't agreed yet</div>
            <p className="text-xs text-muted-foreground">
              {isRequester
                ? "Payment unlocks once you and the counsel agree on a final amount. Head to the Negotiation page to propose or respond to an offer."
                : "This request has an active commercial offer waiting on you. Head to the Negotiation page to accept it, send a counter offer, or decline."}
            </p>
            <Button
              type="button"
              onClick={() => { onOpenChange(false); navigate(`/hearing-requests/${hearingId}/negotiate`); }}
              className="bg-accent hover:bg-accent/90 font-bold"
            >
              <Gavel className="w-4 h-4 mr-1.5" /> Go to Negotiation
            </Button>
          </div>
        )}

        {/* Escrow Module: single source of truth for escrow status/actions —
            same component, same role-aware copy as the Negotiation page, so
            there's never a second, different workflow for the same hearing
            just because it was opened from here instead. */}
        {isEscrowParticipant && (
          <EscrowStagePanel hearingId={hearingId} hearing={hearing} viewerRole={viewerRole} onChanged={() => { onChanged?.(); load(); }} />
        )}

        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1.5">
            Documents ({documents.length})
          </div>
          <div className="space-y-1.5 mb-2">
            {documents.map((d) => (
              <button key={d.doc_id} type="button" onClick={() => openDocument(d.doc_id)}
                      className="w-full flex items-center gap-2 text-sm border rounded-md px-2.5 py-1.5 hover:bg-slate-50 text-left">
                <FileText className="w-4 h-4 text-accent flex-shrink-0" />
                <span className="truncate flex-1">{d.original_filename}</span>
                <Badge variant="outline" className="text-2xs uppercase">{d.kind.replace("_", " ")}</Badge>
              </button>
            ))}
            {!documents.length && <p className="text-sm text-muted-foreground">No documents yet.</p>}
          </div>
          {/* Case documents only — the Court Order Sheet upload now lives
              exclusively in EscrowStagePanel above (rule 5's primary CTA),
              so there's exactly one place to upload it, not two. Gated on
              details_submitted — BlaBlaCar-style flow (founder direction):
              nothing case-specific to attach a document to before the case
              brief itself has been shared. */}
          {(isRequester || isAssignedProxyCounsel) && hearing.details_submitted && (
            <div className="flex items-center gap-2">
              <input ref={fileInputRef} type="file" className="text-xs flex-1" />
              <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => uploadFile("case_document")}>
                <Upload className="w-3.5 h-3.5 mr-1.5" /> Upload Case Document
              </Button>
            </div>
          )}
        </div>

        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1.5">Notes</div>
          <div className="space-y-1 text-xs mb-2 max-h-28 overflow-y-auto">
            {hearing.hearing_notes?.map((n, i) => <div key={i} className="bg-secondary rounded px-2 py-1">{n.text}</div>)}
            {!hearing.hearing_notes?.length && <p className="text-muted-foreground">No notes yet.</p>}
          </div>
          <div className="flex gap-2">
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a hearing note" />
            <Button type="button" variant="outline" onClick={submitNote}>Add</Button>
          </div>
        </div>

        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1.5">Chat</div>
          <div className="space-y-1.5 mb-2 max-h-40 overflow-y-auto">
            {messages.map((m) => {
              const isMine = m.sender_user_id === user?.user_id;
              const time = m.created_at ? new Date(m.created_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "";
              return (
                <div key={m.message_id} className={`flex flex-col ${isMine ? "items-end" : "items-start"}`}>
                  <div className={`text-2xs font-bold text-muted-foreground mb-0.5 px-0.5 ${isMine ? "text-right" : "text-left"}`}>
                    {isMine ? "You" : m.sender_name || "Participant"}
                  </div>
                  <div className={`text-sm rounded-lg px-3 py-1.5 max-w-[80%] ${isMine ? "bg-accent/10" : "bg-secondary"}`}>
                    {m.text}
                    {time && <div className="text-2xs text-muted-foreground mt-0.5">{time}</div>}
                  </div>
                </div>
              );
            })}
            {!messages.length && <p className="text-sm text-muted-foreground">No messages yet.</p>}
          </div>
          <div className="flex gap-2">
            <Input value={messageText} onChange={(e) => setMessageText(e.target.value)} placeholder="Message"
                   onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); sendMessage(); } }} />
            <Button type="button" variant="outline" onClick={sendMessage}><Send className="w-4 h-4" /></Button>
          </div>
        </div>

        <HearingTimeline timeline={hearing.timeline} hearing={hearing} />

        {canRate && (
          <div className="border-t pt-3">
            <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1.5">
              Rate {isRequester ? "the proxy counsel" : "the client"}
            </div>
            <div className="flex gap-1 mb-2">
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} type="button" onClick={() => setRating(n)}>
                  <Star className={`w-6 h-6 ${n <= rating ? "fill-accent text-accent" : "text-slate-300"}`} />
                </button>
              ))}
            </div>
            <Textarea rows={2} value={review} onChange={(e) => setReview(e.target.value)} placeholder="Optional review" className="mb-2" />
            <Button type="button" onClick={submitRating} disabled={busy} className="bg-accent hover:bg-accent/90 font-bold">Submit rating</Button>
          </div>
        )}

        <div className="border-t pt-3 flex flex-wrap gap-2">
          {canAccept && (
            <Button type="button" disabled={busy} onClick={() => run(() => acceptHearingRequest(hearingId))} className="bg-emerald-600 hover:bg-emerald-700 font-bold">
              <CheckCircle2 className="w-4 h-4 mr-1.5" /> Accept
            </Button>
          )}
          {canDecline && (
            <Button type="button" disabled={busy} variant="outline" onClick={() => run(() => declineHearingRequest(hearingId))} className="font-bold">
              <X className="w-4 h-4 mr-1.5" /> Decline
            </Button>
          )}
          {canReject && (
            <Button type="button" disabled={busy} variant="outline" onClick={() => run(() => rejectHearingRequest(hearingId))} className="font-bold text-red-600 border-red-200 hover:bg-red-50">
              <X className="w-4 h-4 mr-1.5" /> Reject
            </Button>
          )}
          {canMarkConducted && (
            <Button type="button" disabled={busy} onClick={() => run(() => markHearingConducted(hearingId))} className="bg-emerald-600 hover:bg-emerald-700 font-bold">
              <CheckCircle2 className="w-4 h-4 mr-1.5" /> Mark Hearing Conducted
            </Button>
          )}
          {canCancel && (
            <Button type="button" disabled={busy} variant="outline" onClick={() => run(() => cancelHearingRequest(hearingId))} className="font-bold text-red-600 border-red-200 hover:bg-red-50 ml-auto">
              <Ban className="w-4 h-4 mr-1.5" /> Cancel Request
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
