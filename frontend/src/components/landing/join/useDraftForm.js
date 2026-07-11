import { useCallback, useEffect, useRef, useState } from "react";
import { createLeadDraft, updateLeadDraft } from "@/lib/leadsApi";

const AUTOSAVE_DEBOUNCE_MS = 500;

/* Local-only draft persistence for a role form. Saves { values, currentStep,
   leadId, draftToken } under `storageKey` so a user can close the browser
   mid-form and resume later — both via the explicit "Save as Draft" button
   and a debounced autosave on every change, so progress isn't lost even if
   the user never clicks it.

   The same autosave path also syncs to the backend leads API (POST
   /leads/draft to mint a lead_id/draft_token on first write, then PUT
   /leads/{id}/draft on every change after). localStorage stays the always-on
   fallback/cache — a page reload before a network round-trip finishes never
   loses data, since the local write happens synchronously and the server
   sync is fire-and-forget except when explicitly awaited via saveDraft(). */
export default function useDraftForm(storageKey, initialValues, roleAppliedFor) {
  const [values, setValues] = useState(initialValues);
  const [currentStep, setCurrentStep] = useState(0);
  const [pendingDraft, setPendingDraft] = useState(null);
  const [leadId, setLeadId] = useState(null);
  const [draftToken, setDraftToken] = useState(null);
  const dirtyRef = useRef(false);
  const autosaveTimer = useRef(null);
  const creatingRef = useRef(null); // in-flight create-draft promise, to dedupe concurrent callers

  useEffect(() => {
    if (!storageKey) return;
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object" && parsed.values) {
          setPendingDraft(parsed);
        }
      }
    } catch {
      /* corrupt draft, ignore */
    }
  }, [storageKey]);

  const writeDraft = useCallback((currentValues, step, ids) => {
    if (!storageKey) return;
    window.localStorage.setItem(storageKey, JSON.stringify({
      values: currentValues,
      currentStep: step,
      leadId: ids?.leadId ?? leadId,
      draftToken: ids?.draftToken ?? draftToken,
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey, leadId, draftToken]);

  // Ensures a server-side draft exists, creating one on first call (dedupes
  // concurrent callers via creatingRef). Returns {leadId, draftToken}.
  const ensureLeadDraft = useCallback(async () => {
    if (leadId && draftToken) return { leadId, draftToken };
    if (creatingRef.current) return creatingRef.current;
    const promise = createLeadDraft(roleAppliedFor, values, currentStep)
      .then(({ lead_id, draft_token }) => {
        setLeadId(lead_id);
        setDraftToken(draft_token);
        writeDraft(values, currentStep, { leadId: lead_id, draftToken: draft_token });
        return { leadId: lead_id, draftToken: draft_token };
      })
      .finally(() => { creatingRef.current = null; });
    creatingRef.current = promise;
    return promise;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leadId, draftToken, roleAppliedFor, values, currentStep, writeDraft]);

  // Debounced autosave — skipped while an un-actioned draft banner is showing,
  // so a fresh mount doesn't silently overwrite a saved draft before the user
  // chooses Resume/Start Fresh.
  useEffect(() => {
    if (!storageKey || !dirtyRef.current || pendingDraft) return undefined;
    if (autosaveTimer.current) clearTimeout(autosaveTimer.current);
    autosaveTimer.current = setTimeout(() => {
      writeDraft(values, currentStep);
      if (leadId && draftToken) {
        updateLeadDraft(leadId, draftToken, values, currentStep).catch(() => {
          /* fail-soft: localStorage already has the latest values */
        });
      }
    }, AUTOSAVE_DEBOUNCE_MS);
    return () => clearTimeout(autosaveTimer.current);
  }, [values, currentStep, storageKey, pendingDraft, writeDraft, leadId, draftToken]);

  const setValue = useCallback((key, val) => {
    dirtyRef.current = true;
    setValues((prev) => ({ ...prev, [key]: val }));
  }, []);

  const resumeDraft = useCallback(() => {
    setPendingDraft((draft) => {
      if (draft) {
        dirtyRef.current = true;
        setValues((prev) => ({ ...prev, ...draft.values }));
        if (typeof draft.currentStep === "number") setCurrentStep(draft.currentStep);
        if (draft.leadId && draft.draftToken) {
          setLeadId(draft.leadId);
          setDraftToken(draft.draftToken);
        }
      }
      return null;
    });
  }, []);

  const discardDraft = useCallback(() => {
    if (storageKey) window.localStorage.removeItem(storageKey);
    setPendingDraft(null);
  }, [storageKey]);

  // Explicit "Save as Draft" click — awaits the server sync so the caller can
  // surface an error if it fails (unlike the silent-fail background autosave).
  const saveDraft = useCallback(async () => {
    dirtyRef.current = true;
    const ids = await ensureLeadDraft();
    writeDraft(values, currentStep, ids);
    await updateLeadDraft(ids.leadId, ids.draftToken, values, currentStep);
  }, [ensureLeadDraft, writeDraft, values, currentStep]);

  const clearDraft = useCallback(() => {
    if (storageKey) window.localStorage.removeItem(storageKey);
    dirtyRef.current = false;
  }, [storageKey]);

  const resetForm = useCallback(() => {
    dirtyRef.current = false;
    setValues(initialValues);
    setCurrentStep(0);
    setLeadId(null);
    setDraftToken(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    values,
    setValue,
    currentStep,
    setCurrentStep,
    hasPendingDraft: !!pendingDraft,
    resumeDraft,
    discardDraft,
    saveDraft,
    clearDraft,
    resetForm,
    leadId,
    draftToken,
    ensureLeadDraft,
  };
}
