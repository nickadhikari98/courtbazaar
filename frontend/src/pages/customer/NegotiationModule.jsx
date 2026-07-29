import React, { useEffect, useState } from "react";
import { useParams, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  ClipboardList, FileStack, Wallet, BadgeCheck, Star, ArrowLeft, Gavel, Loader2, Ban,
} from "lucide-react";
import { getHearingRequest } from "@/lib/hearingRequestsApi";
import { payForHearing as payForHearingShared } from "@/lib/hearingPayment";
import { formatINR } from "@/lib/api";
import { initialsOf } from "@/components/proxyCounsel/CounselCard";
import HearingProgressStepper from "@/components/shared/HearingProgressStepper";
import HearingTimeline from "@/components/shared/HearingTimeline";
import NegotiationChat from "@/components/negotiation/NegotiationChat";
import NegotiationOfferPanel from "@/components/negotiation/NegotiationOfferPanel";
import { useNegotiationPoll } from "@/components/negotiation/useNegotiationPoll";

const STATUS_BADGE = {
  requested: "bg-amber-100 text-amber-700",
  broadcast: "bg-amber-100 text-amber-700",
  accepted: "bg-blue-100 text-blue-700",
  payment_pending: "bg-amber-100 text-amber-700",
  documents_shared: "bg-blue-100 text-blue-700",
  rejected: "bg-red-100 text-red-700",
  cancelled: "bg-red-100 text-red-700",
};

const TERMINAL_STATUSES = ["rejected", "cancelled", "expired"];

// Still genuinely future work, not part of this milestone's ordered list
// (chat / offers / agreement / locking / payment) — see NegotiationChat.jsx
// and NegotiationOfferPanel.jsx for the sections that are now real.
const COMING_SOON_SECTIONS = [
  { icon: ClipboardList, title: "Assignment Discussion", body: "Confirm scope, hearing logistics, and expectations with the counsel." },
  { icon: FileStack, title: "Document Sharing", body: "Share case papers and receive drafts back from the counsel." },
];

/* Navigation target for BOTH selection paths in HireProxyCounsel.jsx (AI
   recommendation or Search More Counsels) — there is exactly one
   post-selection destination. Also reachable from Practice.jsx's
   "Negotiation Requests" section for the targeted advocate — this page is
   role-aware (viewerRole below) rather than having a separate advocate
   variant. */
export default function NegotiationModule() {
  const { hearingId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [hearing, setHearing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const { negotiation, reload: reloadNegotiation } = useNegotiationPoll(hearingId);

  // Passed directly from HireProxyCounsel.jsx at selection time so the rich
  // mock profile (photo, rating, bio, ...) renders immediately without a
  // round trip. No customer-facing "fetch counsel profile by id" API exists
  // today, so a hard refresh or a direct link to this URL falls back to
  // just the target_advocate_id already stored on the hearing (see below).
  const counsel = location.state?.counsel || null;

  const loadHearing = () => getHearingRequest(hearingId)
    .then((data) => setHearing(data))
    .catch(() => toast.error("Could not load this request"));

  useEffect(() => {
    setLoading(true);
    loadHearing().finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once per hearingId
  }, [hearingId]);

  const common = hearing?.request_details?.common || {};
  const viewerRole = hearing?.requesting_user_id === user?.user_id ? "customer" : "counsel";
  const isTerminal = hearing && TERMINAL_STATUSES.includes(hearing.status);
  const agreed = negotiation?.status === "agreed";
  const canPay = viewerRole === "customer" && hearing?.status === "requested" && agreed;

  const handlePay = async () => {
    setPaying(true);
    try {
      await payForHearingShared(hearingId, hearing, user, {
        onSuccess: ({ simulated }) => {
          toast.success(simulated ? "Payment successful (simulated Razorpay) — held by CourtBazaar" : "Payment successful — held by CourtBazaar");
          loadHearing();
        },
      });
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Payment could not be started");
    } finally {
      setPaying(false);
    }
  };

  return (
    <PageContainer className="max-w-5xl">
      <PageHeader
        eyebrow="Proxy Counsel" eyebrowIcon={Gavel} title="Negotiation"
        description="Finalize scope, fee, and documents with your selected counsel before payment."
        action={
          <Button type="button" variant="outline" onClick={() => navigate(viewerRole === "counsel" ? "/practice" : "/hire-proxy-counsel")}>
            <ArrowLeft className="w-4 h-4 mr-1.5" /> Back
          </Button>
        }
      />

      {loading && <div className="text-center text-muted-foreground py-10 mt-6">Loading…</div>}

      {!loading && !hearing && (
        <Card className="border-dashed border-2 mt-6">
          <CardContent className="p-10 text-center text-sm text-muted-foreground">This request could not be found.</CardContent>
        </Card>
      )}

      {!loading && hearing && (
        <div className="mt-6 grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-6 items-start">
          <div className="space-y-6">
            <Card className="dashboard-card border-none">
              <CardContent className="p-5">
                <div className="cb-overline text-accent mb-2">Hearing Summary</div>
                <div className="flex items-center gap-2 mb-3 flex-wrap">
                  <div className="font-display font-bold text-lg">{common.case_title || hearing.court_id}</div>
                  <Badge className={`${STATUS_BADGE[hearing.status] || "bg-slate-100 text-slate-600"} border-0 font-bold uppercase text-2xs`}>
                    {hearing.status.replace(/_/g, " ")}
                  </Badge>
                </div>
                <dl className="grid sm:grid-cols-2 gap-3 text-sm">
                  <div><dt className="text-muted-foreground text-xs">Court</dt><dd className="font-semibold">{common.court_name || hearing.court_id}</dd></div>
                  <div><dt className="text-muted-foreground text-xs">Hearing Date</dt><dd className="font-semibold">{hearing.hearing_date}{common.hearing_time ? ` at ${common.hearing_time}` : ""}</dd></div>
                  <div><dt className="text-muted-foreground text-xs">Priority</dt><dd className="font-semibold">{common.priority || "Normal"}</dd></div>
                  <div><dt className="text-muted-foreground text-xs">{agreed ? "Agreed Fee" : "Reference Fee"}</dt><dd className="font-semibold">{hearing.fee ? formatINR(hearing.fee) : "Not specified"}</dd></div>
                </dl>
                {hearing.case_details && <div className="mt-3 text-sm border rounded-lg p-3 bg-secondary/30">{hearing.case_details}</div>}
                {!isTerminal && <div className="mt-4"><HearingProgressStepper status={hearing.status} compact negotiationAgreed={agreed} /></div>}
              </CardContent>
            </Card>

            {isTerminal ? (
              <Card className="border-dashed border-2">
                <CardContent className="p-8 text-center">
                  <Ban className="w-8 h-8 mx-auto text-red-500 mb-2" strokeWidth={1.5} />
                  <p className="text-sm font-semibold">This request was {hearing.status}.</p>
                  <p className="text-xs text-muted-foreground mt-1">Negotiation is closed — start a new request to try again.</p>
                </CardContent>
              </Card>
            ) : (
              <>
                <NegotiationOfferPanel
                  hearingId={hearingId} negotiation={negotiation} viewerUserId={user?.user_id} viewerRole={viewerRole}
                  // Accepting flips hearing.fee/commercially_locked server-side
                  // (hearings.set_negotiated_fee) in the same call that agrees
                  // the negotiation — reload both so the Hearing Summary's
                  // "Agreed Fee" and payment section never show stale data for
                  // the moment between agreement and the next unrelated refresh.
                  onChanged={async () => { await reloadNegotiation(); loadHearing(); }} onHearingEnded={loadHearing}
                />
                <NegotiationChat hearingId={hearingId} timeline={negotiation?.timeline} negotiationStatus={negotiation?.status} />
              </>
            )}

            <Card className="dashboard-card border-none">
              <CardContent className="p-5">
                <div className="cb-overline text-accent mb-2">Negotiation Timeline</div>
                {hearing.timeline?.length ? <HearingTimeline timeline={hearing.timeline} /> : <p className="text-sm text-muted-foreground">No activity yet.</p>}
              </CardContent>
            </Card>

            {!isTerminal && (
              <div className="grid sm:grid-cols-2 gap-4">
                {COMING_SOON_SECTIONS.map(({ icon: Icon, title, body }) => (
                  <Card key={title} className="dashboard-card border-none border-dashed">
                    <CardContent className="p-5">
                      <div className="flex items-center justify-between mb-2">
                        <Icon className="w-5 h-5 text-accent" />
                        <Badge variant="outline" className="text-2xs font-bold uppercase">Coming Soon</Badge>
                      </div>
                      <div className="font-display font-bold text-sm mb-1">{title}</div>
                      <p className="text-xs text-muted-foreground">{body}</p>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}

            {!isTerminal && hearing.status === "requested" && (
              <Card className="dashboard-card border-none">
                <CardContent className="p-5">
                  <div className="flex items-center justify-between mb-2">
                    <Wallet className="w-5 h-5 text-accent" />
                    {!agreed && <Badge variant="outline" className="text-2xs font-bold uppercase">Locked until agreed</Badge>}
                  </div>
                  <div className="font-display font-bold text-sm mb-1">Final Amount &amp; Escrow Payment</div>
                  {agreed ? (
                    <>
                      <p className="text-xs text-muted-foreground mb-3">
                        Both parties agreed on {formatINR(negotiation.locked_amount)}. {viewerRole === "customer"
                          ? "This will be held securely in escrow by CourtBazaar until the hearing is verified."
                          : "Waiting for the client to complete payment — held securely in escrow until the hearing is verified."}
                      </p>
                      {viewerRole === "customer" && (
                        <Button type="button" onClick={handlePay} disabled={paying} className="bg-accent hover:bg-accent/90 font-bold" data-testid="pay-via-escrow">
                          {paying && <Loader2 className="w-4 h-4 animate-spin mr-1.5" />} Pay {formatINR(negotiation.locked_amount)} via Escrow
                        </Button>
                      )}
                    </>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Payment unlocks once both sides agree on a final amount in Fee Negotiation above.
                    </p>
                  )}
                </CardContent>
              </Card>
            )}
          </div>

          <div>
            <div className="cb-overline text-accent mb-2">{viewerRole === "customer" ? "Selected Counsel" : "Client"}</div>
            {counsel ? (
              <Card className="bento-card border-none">
                <CardContent className="p-4">
                  <div className="flex items-start gap-3">
                    <Avatar className="w-12 h-12 flex-shrink-0">
                      {counsel.avatar_url && <AvatarImage src={counsel.avatar_url} alt={counsel.name} />}
                      <AvatarFallback className="bg-primary text-white text-xs font-bold">{initialsOf(counsel.name)}</AvatarFallback>
                    </Avatar>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <div className="font-display font-bold text-sm truncate">{counsel.name}</div>
                        {counsel.verified && <BadgeCheck className="w-4 h-4 text-accent flex-shrink-0" aria-label="Verified" />}
                      </div>
                      <div className="flex items-center gap-1 text-xs text-muted-foreground mt-0.5">
                        <Star className="w-3 h-3 fill-amber-400 text-amber-400 flex-shrink-0" /> {counsel.rating}
                        {counsel.experience_years != null && <><span className="mx-1">·</span>{counsel.experience_years} yrs</>}
                      </div>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1">
                    {counsel.primary_courts?.map((c) => <Badge key={c} variant="outline" className="text-2xs font-semibold">{c}</Badge>)}
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {counsel.practice_areas?.map((p) => <Badge key={p} variant="outline" className="text-2xs font-semibold text-accent border-accent/30">{p}</Badge>)}
                  </div>
                  {counsel.proposed_fee != null && (
                    <div className="mt-2 text-sm font-bold">{formatINR(counsel.proposed_fee)} <span className="text-xs font-medium text-muted-foreground">reference fee</span></div>
                  )}
                </CardContent>
              </Card>
            ) : (
              <Card className="border-dashed border-2">
                <CardContent className="p-5 text-center text-sm">
                  <div className="font-semibold">{viewerRole === "customer" ? (hearing.target_advocate_id || "—") : (hearing.requesting_user_id || "—")}</div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Full profile will appear here when you arrive from the recommendations screen, or once
                    profiles are available via a public lookup API.
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </PageContainer>
  );
}
