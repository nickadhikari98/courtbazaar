import React, { useEffect, useRef, useState } from "react";
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
import { Star, FileText, Send, Upload, CheckCircle2, X, Ban, ShieldCheck, Loader2 } from "lucide-react";
import {
  getHearingRequest, acceptHearingRequest, declineHearingRequest, rejectHearingRequest, cancelHearingRequest,
  markHearingConducted, rateHearingRequest, addHearingNote, listHearingMessages,
  postHearingMessage, listHearingDocuments, uploadHearingDocument, getHearingDocumentUrl,
  createHearingPaymentOrder, verifyHearingPayment, getHearingEscrow,
} from "@/lib/hearingRequestsApi";
import HearingTimeline from "@/components/shared/HearingTimeline";
import HearingProgressStepper from "@/components/shared/HearingProgressStepper";

const STATUS_BADGE = {
  requested: "bg-amber-100 text-amber-700",
  broadcast: "bg-amber-100 text-amber-700",
  accepted: "bg-blue-100 text-blue-700",
  payment_pending: "bg-amber-100 text-amber-700",
  documents_shared: "bg-blue-100 text-blue-700",
  preparation: "bg-blue-100 text-blue-700",
  hearing_scheduled: "bg-blue-100 text-blue-700",
  hearing_completed: "bg-indigo-100 text-indigo-700",
  verification_pending: "bg-amber-100 text-amber-700",
  verified: "bg-emerald-100 text-emerald-700",
  completed: "bg-emerald-100 text-emerald-700",
  rated: "bg-emerald-100 text-emerald-700",
  rejected: "bg-red-100 text-red-700",
  cancelled: "bg-red-100 text-red-700",
  disputed: "bg-red-100 text-red-700",
  expired: "bg-slate-100 text-slate-600",
};

// Statuses from which the escrow status line ("Payment secured...") makes
// sense to show — payment is now held from "broadcast" onward (M6 reorder:
// payment precedes broadcast/acceptance instead of following it).
const ESCROW_HELD_STATUSES = new Set([
  "broadcast", "accepted", "documents_shared", "preparation", "hearing_scheduled", "hearing_completed",
  "verification_pending", "verified", "completed", "rated",
]);

/* Shared between the advocate side (HireProxyCounsel.jsx) and the proxy
   counsel side (Practice.jsx's Hearings tab) — the same dialog, with
   contextual actions computed from the viewer's relationship to the hearing
   (requester vs assigned proxy counsel) and its current status. */
export default function HearingDetailDialog({ hearingId, open, onOpenChange, onChanged }) {
  const { user } = useAuth();
  const [hearing, setHearing] = useState(null);
  const [messages, setMessages] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [escrow, setEscrow] = useState(null);
  const [note, setNote] = useState("");
  const [messageText, setMessageText] = useState("");
  const [rating, setRating] = useState(5);
  const [review, setReview] = useState("");
  const [busy, setBusy] = useState(false);
  const [paying, setPaying] = useState(false);
  const fileInputRef = useRef(null);

  const load = () => {
    if (!hearingId) return;
    getHearingRequest(hearingId).then(setHearing).catch(() => toast.error("Could not load this hearing"));
    listHearingMessages(hearingId).then(setMessages).catch(() => {});
    listHearingDocuments(hearingId).then(setDocuments).catch(() => {});
    getHearingEscrow(hearingId).then(setEscrow).catch(() => setEscrow(null));
  };
  useEffect(() => { if (open) load(); }, [open, hearingId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!hearing) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-xl"><DialogHeader><DialogTitle>Loading…</DialogTitle></DialogHeader></DialogContent>
      </Dialog>
    );
  }

  const isRequester = hearing.requesting_user_id === user?.user_id;
  const isAssignedProxyCounsel = hearing.proxy_counsel_user_id === user?.user_id;
  const isTargetedAtMe = hearing.target_advocate_id === user?.user_id;
  const isEligibleAdvocate = !isRequester && !isAssignedProxyCounsel && hearing.status === "broadcast"
    && (!hearing.target_advocate_id || isTargetedAtMe);
  const canAccept = isEligibleAdvocate;
  const canDecline = isEligibleAdvocate && !hearing.target_advocate_id;
  const canReject = isEligibleAdvocate && isTargetedAtMe;
  // M6 reorder: payment now happens right after creation, before broadcast.
  const canPay = isRequester && hearing.status === "requested";
  const canCancel = isRequester && ["requested", "broadcast", "accepted", "payment_pending", "documents_shared", "preparation", "hearing_scheduled", "hearing_completed"].includes(hearing.status);
  const canMarkConducted = isAssignedProxyCounsel && hearing.status === "hearing_scheduled";
  const canRate = ["completed", "rated"].includes(hearing.status) && !hearing.rated_by?.includes(user?.user_id)
    && (isRequester || isAssignedProxyCounsel);

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
      const order = await createHearingPaymentOrder(hearingId);
      if (order.simulated) {
        await verifyHearingPayment(hearingId, { razorpay_order_id: order.razorpay_order_id });
        toast.success("Payment successful (simulated Razorpay) — held by CourtBazaar");
        onChanged?.();
        load();
      } else {
        const rzp = new window.Razorpay({
          key: order.key_id,
          amount: order.amount,
          currency: "INR",
          name: "CourtBazaar™",
          description: `Hearing ${hearing.court_id}`,
          order_id: order.razorpay_order_id,
          handler: async (resp) => {
            await verifyHearingPayment(hearingId, resp);
            toast.success("Payment successful — held by CourtBazaar");
            onChanged?.();
            load();
          },
          prefill: { name: user?.name, email: user?.email, contact: user?.phone },
          // eslint-disable-next-line no-restricted-syntax -- Razorpay SDK config object, not a Tailwind-styled element (same exception as OrderDetail.jsx's payRazorpay)
          theme: { color: "#D97706" },
        });
        rzp.open();
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Payment could not be started");
    } finally {
      setPaying(false);
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
            <Badge className={`${STATUS_BADGE[hearing.status] || ""} border-0 font-bold uppercase text-2xs`}>
              {hearing.status.replace(/_/g, " ")}
            </Badge>
          </DialogTitle>
          <DialogDescription>
            Hearing date {hearing.hearing_date}{hearing.fee ? ` · Fee ₹${hearing.fee}` : ""}
          </DialogDescription>
        </DialogHeader>

        <HearingProgressStepper status={hearing.status} />

        <div className="text-sm border rounded-lg p-3 bg-secondary/30">{hearing.case_details}</div>

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

        {ESCROW_HELD_STATUSES.has(hearing.status) && escrow && (
          <div className="flex items-center gap-2 text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
            <ShieldCheck className="w-4 h-4 flex-shrink-0" />
            {escrow.status === "released"
              ? `${formatINR(escrow.payee_amount)} released to the advocate's wallet.`
              : `${formatINR(escrow.amount)} held by CourtBazaar — released after verification.`}
          </div>
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
          {(isRequester || isAssignedProxyCounsel) && (
            <div className="flex items-center gap-2">
              <input ref={fileInputRef} type="file" className="text-xs flex-1" />
              <Button type="button" size="sm" variant="outline" disabled={busy}
                      onClick={() => uploadFile(isAssignedProxyCounsel ? "order_sheet" : "case_document")}>
                <Upload className="w-3.5 h-3.5 mr-1.5" /> Upload
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
            {messages.map((m) => (
              <div key={m.message_id} className={`text-sm rounded-lg px-3 py-1.5 max-w-[80%] ${m.sender_user_id === user?.user_id ? "bg-accent/10 ml-auto" : "bg-secondary"}`}>
                {m.text}
              </div>
            ))}
            {!messages.length && <p className="text-sm text-muted-foreground">No messages yet.</p>}
          </div>
          <div className="flex gap-2">
            <Input value={messageText} onChange={(e) => setMessageText(e.target.value)} placeholder="Message"
                   onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); sendMessage(); } }} />
            <Button type="button" variant="outline" onClick={sendMessage}><Send className="w-4 h-4" /></Button>
          </div>
        </div>

        <HearingTimeline timeline={hearing.timeline} />

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
