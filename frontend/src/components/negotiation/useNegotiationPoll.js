import { useEffect, useRef, useState } from "react";
import { getNegotiation } from "@/lib/negotiationApi";

const POLL_INTERVAL_MS = 5000;

/* Single source of truth for negotiation state (offers/timeline/status),
   shared by NegotiationChat (renders timeline as offer/system feed entries)
   and NegotiationOfferPanel (renders the current-offer action UI) so both
   read the exact same poll instead of two independent, potentially
   inconsistent copies. Recursive setTimeout (matches OrderDetail.jsx's
   existing poll pattern, not setInterval), stops once status leaves "open"
   since no further offer state ever changes after agreement — `reload()` is
   exposed so a propose/accept action can refresh immediately instead of
   waiting for the next tick, same as NegotiationChat does for sent messages. */
export function useNegotiationPoll(hearingId) {
  const [negotiation, setNegotiation] = useState(null);
  const [error, setError] = useState(false);
  const cancelledRef = useRef(false);
  const timerRef = useRef(null);

  const fetchOnce = () => getNegotiation(hearingId).then((neg) => {
    if (cancelledRef.current) return;
    setNegotiation(neg);
    setError(false);
    return neg;
  }).catch(() => {
    if (!cancelledRef.current) setError(true);
  });

  useEffect(() => {
    cancelledRef.current = false;
    const poll = () => {
      fetchOnce().then((neg) => {
        if (cancelledRef.current) return;
        if (!neg || neg.status === "open") timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
      });
    };
    poll();
    return () => { cancelledRef.current = true; clearTimeout(timerRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- poll loop is keyed on hearingId alone
  }, [hearingId]);

  return { negotiation, error, reload: fetchOnce };
}
