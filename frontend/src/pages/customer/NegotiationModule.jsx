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
  ClipboardList, FileStack, BadgeCheck, Star, ArrowLeft, Gavel, Ban, CheckCircle2, History,
} from "lucide-react";
import { getHearingRequest, getHearingCounselProfile } from "@/lib/hearingRequestsApi";
import { payForHearing as payForHearingShared } from "@/lib/hearingPayment";
import { formatINR } from "@/lib/api";
import { initialsOf } from "@/components/proxyCounsel/CounselCard";
import HearingProgressStepper from "@/components/shared/HearingProgressStepper";
import HearingTimeline from "@/components/shared/HearingTimeline";
import NegotiationChat from "@/components/negotiation/NegotiationChat";
import NegotiationOfferPanel from "@/components/negotiation/NegotiationOfferPanel";
import NegotiationNextAction from "@/components/negotiation/NegotiationNextAction";
import EscrowStagePanel from "@/components/negotiation/EscrowStagePanel";
import NegotiationOfferChain from "@/components/negotiation/NegotiationOfferChain";
import { useNegotiationPoll } from "@/components/negotiation/useNegotiationPoll";
import { HEARING_STATUS_BADGE_COLOR, roleAwareStatusLabel, getHearingPermissions } from "@/lib/hearingLifecycle";

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
   variant.

   Single-column layout (founder UX redesign): Hearing Summary → Counsel
   Information (compact strip, not a tall sidebar — a sidebar would put it
   last in DOM order on mobile, breaking the requested 1-6 reading order) →
   Fee Negotiation (PRIMARY) → Discussion Chat (SECONDARY) → Next Action →
   Timeline. No backend/business-logic change — every action here still
   calls the exact same endpoints as before this redesign. */
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
  // profile (rating, bio, ...) renders immediately without a round trip.
  // On refresh or a direct/shared link, router state is gone, so it falls
  // back to fetching the same shape from the counsel-profile endpoint below.
  const [counsel, setCounsel] = useState(location.state?.counsel || null);
  // Brief confirmation screen after "End Negotiation" (see NegotiationOfferPanel.jsx)
  // — polish only, not a gate: auto-advances to counsel selection after a
  // couple seconds, or immediately on "Continue", so the requester doesn't
  // just get silently redirected without knowing why.
  const [negotiationEnded, setNegotiationEnded] = useState(false);

  const loadHearing = () => getHearingRequest(hearingId)
    .then((data) => setHearing(data))
    .catch(() => toast.error("Could not load this request"));

  useEffect(() => {
    setLoading(true);
    loadHearing().finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once per hearingId
  }, [hearingId]);

  const common = hearing?.request_details?.common || {};
  // Production-hardening pass: viewerRole/isTerminal(isClosed)/isEscrowParticipant
  // now come from the same shared resolver HearingDetailDialog.jsx calls —
  // no more independently-derived copies that could disagree between screens.
  const { viewerRole, isClosed: isTerminal, isEscrowParticipant, negotiationRequired, canPay } = getHearingPermissions(hearing, user);
  // "Agreed" is read from hearing.commercially_locked (the field the backend
  // itself checks in initiate_payment/cancel_hearing_request), not from the
  // separately-polled negotiation.status — those two are supposed to always
  // agree (hearings.set_negotiated_fee sets them atomically) but are fetched
  // on different cadences, so deriving "agreed" from the poll risked this
  // page showing a momentarily different answer than every other screen.
  const agreed = !!hearing?.commercially_locked;
  const currentOffer = negotiation?.offers?.find((o) => o.offer_id === negotiation.current_offer_id) || null;
  const isProposer = currentOffer?.proposed_by_user_id === user?.user_id;
  const negotiationStage = agreed ? "agreed" : currentOffer ? (isProposer ? "waiting" : "action_required") : "no_offer";

  useEffect(() => {
    // Only the customer views the targeted counsel's card here (the
    // counter-party sidebar for a counsel viewer is the client, not this
    // endpoint) — skip entirely once router state already supplied it.
    if (counsel || viewerRole !== "customer" || !hearing?.target_advocate_id) return;
    getHearingCounselProfile(hearingId)
      .then(setCounsel)
      .catch(() => {}); // leave the placeholder card if the lookup fails
  }, [counsel, viewerRole, hearing, hearingId]);

  // Ending the negotiation doesn't cancel the request — send the requester
  // straight back to counsel selection with the same case details already
  // filled in (see HireProxyCounsel.jsx's resumeRequest handling), excluding
  // the counsel who just didn't work out from the recommendations list.
  const goToCounselSelection = () => {
    navigate("/hire-proxy-counsel", {
      state: {
        resumeRequest: {
          payload: {
            court_id: hearing.court_id, hearing_date: hearing.hearing_date, case_details: hearing.case_details,
            fee: hearing.fee, matter_id: hearing.matter_id, service_type: hearing.service_type,
            request_details: hearing.request_details,
          },
          excludeAdvocateId: hearing.target_advocate_id,
        },
      },
    });
  };

  // NegotiationOfferPanel's "End Negotiation" only flips this flag — the
  // actual navigation is deferred to the confirmation screen below, so the
  // requester sees what happened instead of an unexplained redirect.
  const handleNegotiationEnded = () => setNegotiationEnded(true);

  useEffect(() => {
    if (!negotiationEnded) return undefined;
    const timer = setTimeout(goToCounselSelection, 2000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- goToCounselSelection reads `hearing`, which is stable for the lifetime of this flag
  }, [negotiationEnded]);

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
      // A prior attempt's create-order step can succeed (hearing.status
      // already moved past "requested" server-side) even when the checkout/
      // verify step after it fails or is abandoned — without this reload,
      // this component's `hearing` stays stale at the pre-payment snapshot,
      // so the Pay button stays visible and every retry is a guaranteed
      // IllegalTransition against the real, already-advanced status.
      loadHearing();
    } finally {
      setPaying(false);
    }
  };

  return (
    <PageContainer className="max-w-3xl">
      <PageHeader
        eyebrow="Proxy Counsel" eyebrowIcon={Gavel} title="Negotiation"
        description="Finalize scope, fee, and documents with your selected counsel before payment."
        action={
          <Button type="button" variant="outline" onClick={() => navigate(viewerRole === "counsel" ? "/practice" : "/hire-proxy-counsel")}>
            <ArrowLeft className="w-4 h-4 mr-1.5" /> Back
          </Button>
        }
      />

      {negotiationEnded ? (
        <Card className="dashboard-card border-none mt-6" data-testid="negotiation-ended-screen">
          <CardContent className="p-10 text-center">
            <CheckCircle2 className="w-10 h-10 mx-auto text-emerald-600 mb-3" />
            <div className="font-display font-bold text-lg">Negotiation Ended</div>
            <p className="text-sm text-muted-foreground mt-1">You can now choose another counsel.</p>
            <Button type="button" className="mt-5 bg-accent hover:bg-accent/90 font-bold" onClick={goToCounselSelection} data-testid="negotiation-ended-continue">
              Continue
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          {loading && <div className="text-center text-muted-foreground py-10 mt-6">Loading…</div>}

          {!loading && !hearing && (
            <Card className="border-dashed border-2 mt-6">
              <CardContent className="p-10 text-center text-sm text-muted-foreground">This request could not be found.</CardContent>
            </Card>
          )}

          {!loading && hearing && (
            <div className="mt-6 space-y-5">
              {/* ① Hearing Summary */}
              <Card className="dashboard-card border-none">
                <CardContent className="p-5">
                  <div className="cb-overline text-accent mb-2">Hearing Summary</div>
                  <div className="flex items-center gap-2 mb-3 flex-wrap">
                    <div className="font-display font-bold text-lg">{common.case_title || hearing.court_id}</div>
                    <Badge className={`${HEARING_STATUS_BADGE_COLOR[hearing.status] || "bg-slate-100 text-slate-600"} border-0 font-bold uppercase text-2xs`}>
                      {roleAwareStatusLabel(hearing, viewerRole)}
                    </Badge>
                  </div>
                  <dl className="grid sm:grid-cols-2 gap-3 text-sm">
                    <div><dt className="text-muted-foreground text-xs">Court</dt><dd className="font-semibold">{common.court_name || hearing.court_id}</dd></div>
                    <div><dt className="text-muted-foreground text-xs">Hearing Date</dt><dd className="font-semibold">{hearing.hearing_date}{common.hearing_time ? ` at ${common.hearing_time}` : ""}</dd></div>
                    <div><dt className="text-muted-foreground text-xs">Priority</dt><dd className="font-semibold">{common.priority || "Normal"}</dd></div>
                    <div><dt className="text-muted-foreground text-xs">{agreed ? "Agreed Fee" : "Reference Fee"}</dt><dd className="font-semibold">{hearing.fee ? formatINR(hearing.fee) : "Not specified"}</dd></div>
                  </dl>
                  {hearing.case_details && <div className="mt-3 text-sm border rounded-lg p-3 bg-secondary/30">{hearing.case_details}</div>}
                </CardContent>
              </Card>

              {/* ② Counsel Information — compact strip, not a tall sidebar */}
              <Card className="bento-card border-none">
                <CardContent className="p-4">
                  <div className="cb-overline text-accent mb-2">{viewerRole === "customer" ? "Counsel Information" : "Client"}</div>
                  {counsel ? (
                    <div className="flex items-center gap-3 flex-wrap">
                      <Avatar className="w-10 h-10 flex-shrink-0">
                        {counsel.avatar_url && <AvatarImage src={counsel.avatar_url} alt={counsel.name} />}
                        <AvatarFallback className="bg-primary text-white text-xs font-bold">{initialsOf(counsel.name)}</AvatarFallback>
                      </Avatar>
                      <div className="flex items-center gap-1.5 min-w-0">
                        <div className="font-display font-bold text-sm truncate">{counsel.name}</div>
                        {counsel.verified && <BadgeCheck className="w-4 h-4 text-accent flex-shrink-0" aria-label="Verified" />}
                      </div>
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Star className="w-3 h-3 fill-amber-400 text-amber-400 flex-shrink-0" /> {counsel.rating}
                        {counsel.experience_years != null && <><span className="mx-1">·</span>{counsel.experience_years} yrs</>}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {counsel.primary_courts?.slice(0, 2).map((c) => <Badge key={c} variant="outline" className="text-2xs font-semibold">{c}</Badge>)}
                        {counsel.practice_areas?.slice(0, 2).map((p) => <Badge key={p} variant="outline" className="text-2xs font-semibold text-accent border-accent/30">{p}</Badge>)}
                      </div>
                      {counsel.proposed_fee != null && (
                        <div className="text-sm font-bold ml-auto">{formatINR(counsel.proposed_fee)} <span className="text-xs font-medium text-muted-foreground">ref. fee</span></div>
                      )}
                    </div>
                  ) : (
                    <div className="text-sm">
                      <div className="font-semibold">{viewerRole === "customer" ? (hearing.target_advocate_id || "—") : (hearing.requesting_user_id || "—")}</div>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {viewerRole === "customer" ? "Loading counsel profile…" : "Client profile lookup isn't available here yet."}
                      </p>
                    </div>
                  )}
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
                  {/* ③ Fee Negotiation — PRIMARY */}
                  <NegotiationOfferPanel
                    hearingId={hearingId} negotiation={negotiation} viewerUserId={user?.user_id} viewerRole={viewerRole} hearing={hearing}
                    // Accepting flips hearing.fee/commercially_locked server-side
                    // (hearings.set_negotiated_fee) in the same call that agrees
                    // the negotiation — reload both so the Hearing Summary's
                    // "Agreed Fee" and payment section never show stale data for
                    // the moment between agreement and the next unrelated refresh.
                    onChanged={async () => { await reloadNegotiation(); loadHearing(); }} onHearingEnded={loadHearing}
                    onNegotiationEnded={handleNegotiationEnded}
                  />

                  {/* ④ Discussion Chat — SECONDARY */}
                  <NegotiationChat hearingId={hearingId} timeline={negotiation?.timeline} negotiationStatus={negotiation?.status} hearing={hearing} />

                  {/* ⑤ Next Action — pre-payment/payment stages */}
                  {negotiation && (
                    <NegotiationNextAction
                      stage={negotiationStage} viewerRole={viewerRole} hearing={hearing} canPay={canPay}
                      paying={paying} onPay={handlePay}
                    />
                  )}

                  {/* Escrow Module: post-payment operational lifecycle — escrow-held
                      messaging, order sheet upload, Verify Hearing / Raise Dispute.
                      Self-guards on hearing.status, mutually exclusive with
                      NegotiationNextAction above (never both render at once).
                      isEscrowParticipant-gated to match HearingDetailDialog.jsx —
                      an admin viewing this page must never see it either. */}
                  {isEscrowParticipant && (
                    <EscrowStagePanel hearingId={hearingId} hearing={hearing} viewerRole={viewerRole} onChanged={loadHearing} />
                  )}
                </>
              )}

              {/* ⑥ Timeline */}
              <Card className="dashboard-card border-none">
                <CardContent className="p-5 space-y-4">
                  <div className="cb-overline text-accent">Timeline</div>
                  <NegotiationOfferChain negotiation={negotiation} />
                  {!isTerminal && <HearingProgressStepper status={hearing.status} negotiationAgreed={agreed} targeted={negotiationRequired} />}
                  {hearing.timeline?.length ? (
                    <details>
                      <summary className="text-xs font-bold uppercase tracking-wide text-muted-foreground cursor-pointer flex items-center gap-1.5">
                        <History className="w-3.5 h-3.5" /> Full activity log
                      </summary>
                      <div className="mt-2"><HearingTimeline timeline={hearing.timeline} /></div>
                    </details>
                  ) : (
                    <p className="text-sm text-muted-foreground">No activity yet.</p>
                  )}
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
            </div>
          )}
        </>
      )}
    </PageContainer>
  );
}
