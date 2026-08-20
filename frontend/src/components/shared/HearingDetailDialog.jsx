import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { jsPDF } from "jspdf";
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
import { Star, FileText, Send, Upload, Download, CheckCircle2, X, Ban, Loader2, Gavel } from "lucide-react";
import {
  getHearingRequest, acceptHearingRequest, declineHearingRequest, rejectHearingRequest, cancelHearingRequest,
  markHearingConducted, rateHearingRequest, addHearingNote, listHearingMessages,
  postHearingMessage, listHearingDocuments, uploadHearingDocument, getHearingDocumentUrl,
  submitHearingCaseDetails,
} from "@/lib/hearingRequestsApi";
import { payForHearing as payForHearingShared } from "@/lib/hearingPayment";
import HearingTimeline from "@/components/shared/HearingTimeline";
import HearingProgressStepper from "@/components/shared/HearingProgressStepper";
import DocumentPreviewDialog from "@/components/shared/DocumentPreviewDialog";
import EscrowStagePanel from "@/components/negotiation/EscrowStagePanel";
import ProxyCounselCaseDetailsForm from "@/components/proxyCounsel/ProxyCounselCaseDetailsForm";
import { HEARING_STATUS_BADGE_COLOR, roleAwareStatusLabel, getHearingPermissions } from "@/lib/hearingLifecycle";

/* Shared between the advocate side (HireProxyCounsel.jsx) and the proxy
   counsel side (Practice.jsx's Hearings tab) — the same dialog, with
   contextual actions computed from the viewer's relationship to the hearing
   (requester vs assigned proxy counsel) and its current status. */
// showActivityHistory defaults on: for most callers (Dashboard, Practice,
// HireProxyCounsel) this dialog is the ONLY place the hearing's event log is
// shown. NegotiationModule passes it false because that page already renders a
// dedicated, always-visible Activity History card — keeping it here too would
// just make this dialog longer and duplicate it.
export default function HearingDetailDialog({ hearingId, open, onOpenChange, onChanged, showActivityHistory = true }) {
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
  const [preview, setPreview] = useState(null); // { url, filename } — in-page document preview
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
    isRequester, isAssignedProxyCounsel, canAccept, canDecline, canReject,
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

  const openDocument = async (docId, filename) => {
    try {
      // inline: true — renders in the DocumentPreviewDialog below instead of
      // forcing a download or hopping to a new tab, so it can be checked
      // right there on the same page.
      const { url } = await getHearingDocumentUrl(hearingId, docId, { inline: true });
      setPreview({ url, filename });
    } catch {
      toast.error("Could not open this document");
    }
  };

  // Case details/instructions are plain text baked into the hearing record,
  // not a stored file — no backend export endpoint exists (or is needed)
  // for this, so the PDF is built client-side (jsPDF) from the same fields
  // already rendered above.
  const downloadCaseDetails = () => {
    const c = hearing.request_details?.common || {};
    const s = hearing.request_details?.service_specific || {};
    const lines = [
      c.case_title ? `Case Title: ${c.case_title}` : null,
      c.case_number ? `Case Number: ${c.case_number}` : null,
      c.case_type ? `Case Type: ${c.case_type}` : null,
      c.case_stage ? `Stage: ${c.case_stage}` : null,
      `Hearing Date: ${hearing.hearing_date}${c.hearing_time ? ` at ${c.hearing_time}` : ""}`,
      c.priority ? `Priority: ${c.priority}` : null,
      s.work_required?.length ? `Work Required: ${s.work_required.join(", ")}${s.work_required_notes ? ` — ${s.work_required_notes}` : ""}` : null,
    ].filter((l) => l !== null);

    const doc = new jsPDF({ unit: "pt", format: "a4" });
    const marginX = 48;
    const pageWidth = doc.internal.pageSize.getWidth();
    const wrapWidth = pageWidth - marginX * 2;
    let y = 56;

    doc.setFont("helvetica", "bold");
    doc.setFontSize(16);
    doc.text(`Case Details — ${hearing.court_id}`, marginX, y);
    y += 28;

    doc.setFont("helvetica", "normal");
    doc.setFontSize(11);
    lines.forEach((line) => {
      doc.splitTextToSize(line, wrapWidth).forEach((row) => {
        if (y > doc.internal.pageSize.getHeight() - 48) { doc.addPage(); y = 56; }
        doc.text(row, marginX, y);
        y += 16;
      });
    });

    y += 8;
    doc.setFont("helvetica", "bold");
    doc.text("Instructions", marginX, y);
    y += 18;
    doc.setFont("helvetica", "normal");
    doc.splitTextToSize(hearing.case_details || "", wrapWidth).forEach((row) => {
      if (y > doc.internal.pageSize.getHeight() - 48) { doc.addPage(); y = 56; }
      doc.text(row, marginX, y);
      y += 16;
    });

    doc.save(`case-details-${hearing.hearing_id}.pdf`);
  };

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto cb-scroll">
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
            show yet (status line, for the counsel/other viewer). Shown to
            every viewer (requester and proxy counsel alike) — this used to
            render only the free-text case_details field, silently dropping
            case_title/case_number/case_type/case_stage/hearing_time/priority/
            work_required (all submitted by the same form, stored on
            request_details.common/.service_specific — see
            ProxyCounselCaseDetailsForm), so the counsel never actually saw
            the case brief, just an unlabeled instructions blob. */}
        {hearing.details_submitted ? (
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Case Details</div>
              <button type="button" onClick={downloadCaseDetails} className="flex items-center gap-1 text-2xs font-semibold text-accent hover:underline" data-testid="download-case-details">
                <Download className="w-3.5 h-3.5" /> Download
              </button>
            </div>
            <div className="border rounded-lg p-3 bg-secondary/30 space-y-2 text-sm">
              <div className="grid sm:grid-cols-2 gap-x-4 gap-y-1.5">
                {hearing.request_details?.common?.case_title && (
                  <div><span className="text-muted-foreground">Case Title:</span> <span className="font-medium">{hearing.request_details.common.case_title}</span></div>
                )}
                {hearing.request_details?.common?.case_number && (
                  <div><span className="text-muted-foreground">Case Number:</span> <span className="font-medium">{hearing.request_details.common.case_number}</span></div>
                )}
                {hearing.request_details?.common?.case_type && (
                  <div><span className="text-muted-foreground">Case Type:</span> <span className="font-medium">{hearing.request_details.common.case_type}</span></div>
                )}
                {hearing.request_details?.common?.case_stage && (
                  <div><span className="text-muted-foreground">Stage:</span> <span className="font-medium">{hearing.request_details.common.case_stage}</span></div>
                )}
                {hearing.request_details?.common?.hearing_time && (
                  <div><span className="text-muted-foreground">Hearing Time:</span> <span className="font-medium">{hearing.request_details.common.hearing_time}</span></div>
                )}
                {hearing.request_details?.common?.priority && (
                  <div><span className="text-muted-foreground">Priority:</span> <span className="font-medium">{hearing.request_details.common.priority}</span></div>
                )}
              </div>
              {!!hearing.request_details?.service_specific?.work_required?.length && (
                <div>
                  <span className="text-muted-foreground">Work Required:</span>{" "}
                  <span className="font-medium">{hearing.request_details.service_specific.work_required.join(", ")}</span>
                  {hearing.request_details.service_specific.work_required_notes && (
                    <span className="text-muted-foreground"> — {hearing.request_details.service_specific.work_required_notes}</span>
                  )}
                </div>
              )}
              <div className="pt-1.5 border-t">
                <span className="text-2xs font-bold uppercase tracking-wide text-muted-foreground">Instructions</span>
                <p className="mt-0.5">{hearing.case_details}</p>
              </div>
            </div>
          </div>
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
              <button key={d.doc_id} type="button" onClick={() => openDocument(d.doc_id, d.original_filename)}
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
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <input ref={fileInputRef} type="file" className="text-xs flex-1" />
                <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => uploadFile("case_document")}>
                  {/* Role-aware label: the counsel's headline deliverable is the
                      Court Order Sheet (uploaded from the Escrow panel above at
                      hearing_completed — deliberately ONE upload point, see
                      EscrowStagePanel), so this generic slot is only for their
                      supporting papers and is labelled as such to avoid it being
                      mistaken for the order-sheet upload. */}
                  <Upload className="w-3.5 h-3.5 mr-1.5" /> {isAssignedProxyCounsel ? "Upload Supporting Document" : "Upload Case Document"}
                </Button>
              </div>
              {isAssignedProxyCounsel && (
                <p className="text-2xs text-muted-foreground">
                  Uploading the <span className="font-semibold text-foreground">Court Order Sheet</span>? That's done from the <span className="font-semibold text-foreground">Escrow panel above</span>, once the hearing is marked conducted — not here.
                </p>
              )}
            </div>
          )}
        </div>

        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1.5">Notes</div>
          <div className="space-y-1 text-xs mb-2 max-h-28 overflow-y-auto cb-scroll">
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
          <div className="space-y-1.5 mb-2 max-h-40 overflow-y-auto cb-scroll">
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

        {showActivityHistory && <HearingTimeline timeline={hearing.timeline} hearing={hearing} />}

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
    <DocumentPreviewDialog
      open={!!preview}
      onOpenChange={(v) => { if (!v) setPreview(null); }}
      url={preview?.url}
      filename={preview?.filename}
    />
    </>
  );
}
