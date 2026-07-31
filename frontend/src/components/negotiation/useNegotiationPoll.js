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
  // Guards a real race: the background poll tick and a manual reload() (fired
  // right after propose/accept so the actor's own action reflects instantly,
  // not on the next 5s tick) can both have a GET in flight at once. Without
  // this, whichever response's network round-trip happens to land LAST wins
  // — if that's the poll tick that was issued a moment before the mutation
  // landed server-side, it silently overwrites the just-submitted offer with
  // stale data (exactly the "my own counter-offer doesn't show" bug). Only
  // ever commit the response to the most recently issued request; a slower,
  // now-superseded request's response is simply dropped, not applied.
  const requestSeqRef = useRef(0);

  const fetchOnce = () => {
    const seq = ++requestSeqRef.current;
    return getNegotiation(hearingId).then((neg) => {
      if (cancelledRef.current || seq !== requestSeqRef.current) return neg;
      setNegotiation(neg);
      setError(false);
      return neg;
    }).catch(() => {
      if (!cancelledRef.current && seq === requestSeqRef.current) setError(true);
    });
  };

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
