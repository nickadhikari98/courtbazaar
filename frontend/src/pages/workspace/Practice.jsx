import React, { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import PageContainer from "@/components/layout/PageContainer";
import PageHeader from "@/components/layout/PageHeader";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableEmpty, TableLoading,
} from "@/components/ui/table";
import { Briefcase, X, Plus, Trash2, Star, CheckCircle2, Clock, ArrowRight, Loader2, Pencil, AlertTriangle, XCircle } from "lucide-react";
import {
  getPracticeProfile, updatePracticeProfile, listAvailabilitySlots,
  addAvailabilitySlot, updateAvailabilitySlot, removeAvailabilitySlot, getPracticePerformance,
  getPracticeVisibility,
} from "@/lib/practiceApi";
import { listHearingRequests } from "@/lib/hearingRequestsApi";
import { getCourt, searchCourts } from "@/lib/referenceDataApi";
import { formatINR, getErrorMessage } from "@/lib/api";
import { resolveDateBound } from "@/lib/utils";
import HearingDetailDialog from "@/components/shared/HearingDetailDialog";
import HearingActivityPreview from "@/components/shared/HearingActivityPreview";
import CapabilitiesCard from "@/components/shared/CapabilitiesCard";
import StatGrid from "@/components/shared/StatGrid";
import Loading from "@/components/shared/Loading";
import { useAuth } from "@/context/AuthContext";
import {
  HEARING_STATUS_BADGE_COLOR, roleAwareStatusLabel, getViewerRole,
  isHearingActive, COMPLETED_HEARING_STATUSES, CLOSED_HEARING_STATUSES, counselRespondsViaNegotiation,
} from "@/lib/hearingLifecycle";
import {
  PRICING_SLOTS, PRICING_SLOT_LABELS, PRICING_COURT_TYPES, PRICING_COURT_TYPE_LABELS,
  EXPERIENCE_BRACKETS, pricingMinimum, TIME_OF_DAY_OPTIONS,
} from "@/config/proxyCounselPricing";

const HEARING_TAB_LABELS = { active: "Active", completed: "Completed", cancelled: "Cancelled" };

// Mirrors roleFormData.js's "Maximum Distance You Are Willing to Travel for
// Appearance" / "Availability" radio options exactly — same duplicated-config
// tradeoff already accepted for EXPERIENCE_BRACKETS/PRICING_MINIMUMS (see
// config/proxyCounselPricing.js), so a lead approved through leads.py's
// _derive_practice_profile_patch always lands on a value this Select
// actually has an option for.
const MAX_TRAVEL_DISTANCE_OPTIONS = ["Up to 10 KM", "Up to 25 KM", "Up to 50 KM", "Up to 100 KM", "Any Distance"];
const SCHEDULE_TYPE_OPTIONS = ["Full Time", "Part Time", "Weekdays Only", "Weekends Only"];

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const KINDS = [
  { value: "recurring_weekly", label: "Weekly recurring" },
  { value: "custom_date", label: "Custom date" },
  { value: "holiday_block", label: "Holiday (blocked)" },
  { value: "emergency_unavailable", label: "Emergency unavailable" },
];

/* Simple chip-input for a string[] field (practice areas / courts /
   languages) — local to this page, not promoted to a global ui primitive
   since nothing else needs a tag input yet. */
function TagInput({ label, value, onChange, placeholder }) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const v = draft.trim();
    if (v && !value.includes(v)) onChange([...value, v]);
    setDraft("");
  };
  return (
    <div>
      <Label>{label}</Label>
      <div className="flex flex-wrap gap-1.5 mb-2 mt-1.5">
        {value.map((tag) => (
          <Badge key={tag} variant="outline" className="gap-1 font-semibold">
            {tag}
            <button type="button" onClick={() => onChange(value.filter((t) => t !== tag))}>
              <X className="w-3 h-3" />
            </button>
          </Badge>
        ))}
      </div>
      <div className="flex gap-2">
        <Input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={placeholder}
               onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} />
        {/* Same fade/bright "ready to submit" signal as the Availability
            tab's Add button — faded while there's nothing typed to add yet,
            bright the moment there is. */}
        <Button
          type="button" onClick={add}
          className={draft.trim()
            ? "bg-accent hover:bg-accent/90 font-bold"
            : "bg-accent/50 hover:bg-accent/60 font-bold"}
        >
          <Plus className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
}

/* Bug fix: "Courts" used to be a free-text TagInput — a counsel could type
   "Gujarat High Court" and it would display fine everywhere (it's just
   shown as typed), but list_and_recommend/public_proxy_counsels filter
   proxy_counsel_profiles.courts by real court_id ($in a set of ids looked
   up from the courts collection), so free text never matched and the
   counsel silently never showed up when someone searched/selected that
   court. This picks real courts by name (searchCourts, same /courts?q=
   endpoint the public Court Directory uses) and stores court_id — display
   names for already-saved ids are resolved lazily below, so legacy
   free-text rows (pre-fix) still render as a removable chip instead of a
   raw id, they just won't match search until re-picked from here. */
function CourtPicker({
  label, value, onChange,
  hint = "Pick real courts from search — these are what a Counsel's court filter actually matches against.",
  placeholder = "Search a court by name, e.g. Gujarat High Court",
  testId = "courts-picker-search",
}) {
  const [nameById, setNameById] = useState({});
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const missing = value.filter((id) => !(id in nameById));
    if (!missing.length) return;
    let cancelled = false;
    Promise.all(missing.map((id) => getCourt(id).then((c) => [id, c.name]).catch(() => [id, id])))
      .then((pairs) => { if (!cancelled) setNameById((prev) => ({ ...prev, ...Object.fromEntries(pairs) })); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-run when `value` gains an id we haven't resolved yet
  }, [value]);

  useEffect(() => {
    if (query.trim().length < 2) { setResults([]); return undefined; }
    const t = setTimeout(() => {
      searchCourts(query.trim()).then((list) => setResults(list.slice(0, 20))).catch(() => setResults([]));
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  const add = (court) => {
    if (!value.includes(court.court_id)) {
      setNameById((prev) => ({ ...prev, [court.court_id]: court.name }));
      onChange([...value, court.court_id]);
    }
    setQuery("");
    setResults([]);
    setOpen(false);
  };
  const remove = (id) => onChange(value.filter((v) => v !== id));

  return (
    <div>
      <Label>{label}</Label>
      <div className="flex flex-wrap gap-1.5 mb-2 mt-1.5">
        {value.map((id) => (
          <Badge key={id} variant="outline" className="gap-1 font-semibold">
            {nameById[id] || id}
            <button type="button" onClick={() => remove(id)}>
              <X className="w-3 h-3" />
            </button>
          </Badge>
        ))}
      </div>
      <div className="relative">
        <Input
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder={placeholder}
          data-testid={testId}
        />
        {open && results.length > 0 && (
          <div className="absolute z-20 mt-1 w-full bg-white border border-border rounded-lg shadow-lg max-h-56 overflow-y-auto cb-scroll">
            {results.map((c) => (
              <button
                key={c.court_id} type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => add(c)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-secondary flex items-center justify-between gap-2"
              >
                <span className="truncate">{c.name}</span>
                <span className="text-2xs text-muted-foreground uppercase flex-shrink-0">{c.type?.replace("_", " ")}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      <p className="text-2xs text-muted-foreground mt-1">{hint}</p>
    </div>
  );
}

function ProfileTab({ profile, onSaved }) {
  const { user } = useAuth();
  const [form, setForm] = useState(profile);
  const [saving, setSaving] = useState(false);
  const [savingAvailability, setSavingAvailability] = useState(false);
  const [savingInstant, setSavingInstant] = useState(false);
  const [savingNegotiation, setSavingNegotiation] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setPricing = (courtType, slot, value) => {
    setForm((f) => ({
      ...f,
      pricing: { ...f.pricing, [courtType]: { ...(f.pricing?.[courtType] || {}), [slot]: value === "" ? undefined : Number(value) } },
    }));
  };

  const hasInvalidPricing = () => PRICING_COURT_TYPES.some((courtType) => PRICING_SLOTS.some((slot) => {
    const amount = form.pricing?.[courtType]?.[slot];
    return amount != null && amount < pricingMinimum(courtType, slot, form.experience_bracket);
  }));

  const save = async () => {
    for (const courtType of PRICING_COURT_TYPES) {
      for (const slot of PRICING_SLOTS) {
        const amount = form.pricing?.[courtType]?.[slot];
        const minimum = pricingMinimum(courtType, slot, form.experience_bracket);
        if (amount != null && amount < minimum) {
          toast.error(`${PRICING_COURT_TYPE_LABELS[courtType]} / ${PRICING_SLOT_LABELS[slot]} must be at least ₹${minimum}`);
          return;
        }
      }
    }
    setSaving(true);
    try {
      const updated = await updatePracticeProfile({
        state_bar_council: form.state_bar_council, bar_council_number: form.bar_council_number,
        practice_areas: form.practice_areas, courts: form.courts, languages: form.languages,
        experience_bracket: form.experience_bracket, education: form.education, bio: form.bio,
        professional_status: form.professional_status, max_travel_distance: form.max_travel_distance,
        schedule_type: form.schedule_type, matters_handled: form.matters_handled,
        office_address: form.office_address, fee_structure: form.fee_structure, pricing: form.pricing,
        availability_mode: form.availability_mode, instant_booking: form.instant_booking,
        negotiation_enabled: form.negotiation_enabled,
      });
      onSaved(updated);
      toast.success("Profile saved");
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not save profile"));
    } finally {
      setSaving(false);
    }
  };

  // Toggle switches save on their own, immediately, via the inline "Save"
  // button beside them — not the big "Save profile" button below, which is
  // easy to miss after just flipping a switch and can be a scroll away.
  // Sends only the one field (the PUT is a partial update, exclude_unset on
  // the backend) so it can't accidentally persist unrelated in-progress edits
  // sitting elsewhere in the form.
  const saveToggle = async (key, setBusy, successLabel = "Availability updated") => {
    setBusy(true);
    try {
      const updated = await updatePracticeProfile({ [key]: form[key] });
      onSaved(updated);
      toast.success(successLabel);
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not save"));
    } finally {
      setBusy(false);
    }
  };

  // Instant booking's own save — the Urgent fee inputs live in this same
  // card (see below), always shown regardless of the toggle, so this
  // button saves instant_booking together with the full pricing object
  // (not just the urgent slot) — same "always resend the whole grid"
  // convention save() below already uses, since the backend replaces
  // pricing wholesale rather than merging it field-by-field.
  const saveInstantBooking = async () => {
    for (const courtType of PRICING_COURT_TYPES) {
      const amount = form.pricing?.[courtType]?.urgent;
      const minimum = pricingMinimum(courtType, "urgent", form.experience_bracket);
      if (amount != null && amount < minimum) {
        toast.error(`${PRICING_COURT_TYPE_LABELS[courtType]} Urgent fee must be at least ₹${minimum}`);
        return;
      }
    }
    setSavingInstant(true);
    try {
      const updated = await updatePracticeProfile({ instant_booking: form.instant_booking, pricing: form.pricing });
      onSaved(updated);
      toast.success("Instant booking updated");
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not save"));
    } finally {
      setSavingInstant(false);
    }
  };

  return (
    <div className="space-y-4">
      <CapabilitiesCard user={user} />
      <Card className="dashboard-card border-none">
        <CardContent className="p-5 flex items-center justify-between gap-4">
          <div>
            <div className="font-display font-bold">Available for hearings</div>
            <p className="text-xs text-muted-foreground">Turn off if you're not taking new requests right now.</p>
          </div>
          <div className="flex items-center gap-3">
            <Switch checked={!!form.availability_mode} onCheckedChange={(v) => set("availability_mode", v)} />
            <Button
              type="button" size="sm" onClick={() => saveToggle("availability_mode", setSavingAvailability)}
              disabled={savingAvailability}
              className={form.availability_mode
                ? "bg-accent hover:bg-accent/90 font-bold"
                : "bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold"}
            >
              Save
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card className="dashboard-card border-none">
        <CardContent className="p-5 space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="font-display font-bold">Instant booking</div>
              <p className="text-xs text-muted-foreground">Skip manual accept for requests that match your availability.</p>
            </div>
            <div className="flex items-center gap-3">
              <Switch checked={!!form.instant_booking} onCheckedChange={(v) => set("instant_booking", v)} data-testid="instant-booking-toggle" />
              <Button
                type="button" size="sm" onClick={saveInstantBooking}
                disabled={savingInstant}
                className={form.instant_booking
                  ? "bg-accent hover:bg-accent/90 font-bold"
                  : "bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold"}
              >
                Save
              </Button>
            </div>
          </div>
          {/* This is now the single place to set the Urgent fee — always
              shown here, not just while instant booking is on (a counsel
              can price urgent work without opting into auto-accept), and
              removed from the Availability & Pricing grid below, which
              used to render it a second time (see PRICING_SLOTS.filter
              there). Founder direction (2026-08) was originally to surface
              it here only when instant booking is on so a counsel wouldn't
              have to scroll down for it; now it just lives here full stop. */}
          <div className="pt-4 border-t">
            <div className="flex items-center gap-1.5 text-sm font-bold mb-1">
              <Clock className="w-3.5 h-3.5 text-amber-600" /> Urgent (same-day) fee
            </div>
            <p className="text-xs text-muted-foreground mb-3">
              Shown to clients making an urgent request, whether or not instant booking is on.
            </p>
            <div className="grid sm:grid-cols-2 gap-3">
              {PRICING_COURT_TYPES.map((courtType) => {
                const minimum = pricingMinimum(courtType, "urgent", form.experience_bracket);
                const amount = form.pricing?.[courtType]?.urgent;
                const belowMin = amount != null && amount < minimum;
                return (
                  <div key={courtType}>
                    <Label>{PRICING_COURT_TYPE_LABELS[courtType]}</Label>
                    <Input
                      type="number" min={minimum}
                      value={amount ?? ""}
                      onChange={(e) => setPricing(courtType, "urgent", e.target.value)}
                      placeholder={`Min ₹${minimum}`}
                      onWheel={(e) => e.target.blur()}
                      className={belowMin ? "border-red-500 focus-visible:ring-red-500" : undefined}
                      aria-invalid={belowMin || undefined}
                      data-testid={`instant-urgent-fee-${courtType}`}
                    />
                    {belowMin ? (
                      <p className="text-2xs text-red-600 mt-0.5">Must be at least ₹{minimum}</p>
                    ) : (
                      <p className="text-2xs text-muted-foreground mt-0.5">Min ₹{minimum}</p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="dashboard-card border-none">
        <CardContent className="p-5 flex items-center justify-between gap-4">
          <div>
            <div className="font-display font-bold">Fee negotiation</div>
            <p className="text-xs text-muted-foreground">
              Turn this on to also see a
              Negotiate option and respond to counter offers.
            </p>
          </div>
          <div className="flex items-center gap-3 flex-shrink-0">
            <Switch checked={!!form.negotiation_enabled} onCheckedChange={(v) => set("negotiation_enabled", v)} data-testid="negotiation-enabled-toggle" />
            <Button
              type="button" size="sm" onClick={() => saveToggle("negotiation_enabled", setSavingNegotiation, "Fee negotiation updated")}
              disabled={savingNegotiation}
              className={form.negotiation_enabled
                ? "bg-accent hover:bg-accent/90 font-bold"
                : "bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold"}
            >
              Save
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="dashboard-card border-none">
        <CardContent className="p-5 space-y-4">
          <div className="flex items-center gap-2">
            <span className="font-display font-bold">Verification</span>
            <Badge className={form.kyc_status === "approved" ? "bg-emerald-100 text-emerald-700 border-0" : "bg-amber-100 text-amber-700 border-0"}>
              {form.kyc_status}
            </Badge>
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <Label>Total Years of Practice</Label>
              <Select value={form.experience_bracket || undefined} onValueChange={(v) => set("experience_bracket", v)}>
                <SelectTrigger data-testid="experience-bracket"><SelectValue placeholder="Select range" /></SelectTrigger>
                <SelectContent>
                  {EXPERIENCE_BRACKETS.map((b) => <SelectItem key={b.key} value={b.key}>{b.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Education</Label>
              <Input value={form.education || ""} onChange={(e) => set("education", e.target.value)} />
            </div>
            <div>
              <Label>State Bar Council</Label>
              <Input value={form.state_bar_council || ""} onChange={(e) => set("state_bar_council", e.target.value)} />
            </div>
            <div>
              <Label>Bar Council Enrollment Number</Label>
              <Input value={form.bar_council_number || ""} onChange={(e) => set("bar_council_number", e.target.value)} />
            </div>
            <div>
              <Label>Current Professional Status</Label>
              <Input value={form.professional_status || ""} onChange={(e) => set("professional_status", e.target.value)} />
            </div>
            <div>
              <Label>Maximum Distance Willing to Travel</Label>
              <Select value={form.max_travel_distance || undefined} onValueChange={(v) => set("max_travel_distance", v)}>
                <SelectTrigger><SelectValue placeholder="Select distance" /></SelectTrigger>
                <SelectContent>
                  {MAX_TRAVEL_DISTANCE_OPTIONS.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Availability Schedule</Label>
              <Select value={form.schedule_type || undefined} onValueChange={(v) => set("schedule_type", v)}>
                <SelectTrigger><SelectValue placeholder="Select schedule" /></SelectTrigger>
                <SelectContent>
                  {SCHEDULE_TYPE_OPTIONS.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Approximate Number of Matters Handled</Label>
              <Input
                type="number" min={0} value={form.matters_handled ?? ""}
                onChange={(e) => set("matters_handled", e.target.value === "" ? undefined : Number(e.target.value))}
                onWheel={(e) => e.target.blur()}
              />
            </div>
          </div>
          <div>
            <Label>Bio</Label>
            <Textarea rows={3} value={form.bio || ""} onChange={(e) => set("bio", e.target.value)} />
          </div>
          <div>
            <Label>Office address</Label>
            <Input value={form.office_address || ""} onChange={(e) => set("office_address", e.target.value)} />
          </div>
          <div>
            <Label>Fee structure</Label>
            <Textarea rows={2} value={form.fee_structure || ""} onChange={(e) => set("fee_structure", e.target.value)} placeholder="e.g. ₹2,000 per appearance" />
          </div>
          <TagInput label="Practice areas" value={form.practice_areas || []} onChange={(v) => set("practice_areas", v)} placeholder="e.g. Civil, Criminal" />
          <CourtPicker label="Courts" value={form.courts || []} onChange={(v) => set("courts", v)} />
          <TagInput label="Languages" value={form.languages || []} onChange={(v) => set("languages", v)} placeholder="e.g. Hindi, English" />
          <Button type="button" onClick={save} disabled={saving} className="bg-accent hover:bg-accent/90 font-bold">Save profile</Button>
        </CardContent>
      </Card>

      <Card className="dashboard-card border-none">
        <CardContent className="p-5 space-y-4">
          <div>
            <div className="font-display font-bold">Pricing</div>
            <p className="text-xs text-muted-foreground mt-0.5">Set your own price per slot — never below the platform minimum shown under each field. Leave a slot blank if you don't take that kind of work.</p>
          </div>
          {PRICING_COURT_TYPES.map((courtType) => (
            <div key={courtType}>
              <div className="text-sm font-bold mb-2">{PRICING_COURT_TYPE_LABELS[courtType]}</div>
              {/* "urgent" excluded here — it's set once, above, in the
                  Instant Booking card, not duplicated in this grid too. */}
              <div className="grid sm:grid-cols-3 gap-3">
                {PRICING_SLOTS.filter((slot) => slot !== "urgent").map((slot) => {
                  const minimum = pricingMinimum(courtType, slot, form.experience_bracket);
                  const amount = form.pricing?.[courtType]?.[slot];
                  const belowMin = amount != null && amount < minimum;
                  return (
                    <div key={slot}>
                      <Label>{PRICING_SLOT_LABELS[slot]}</Label>
                      <Input
                        type="number" min={minimum}
                        value={amount ?? ""}
                        onChange={(e) => setPricing(courtType, slot, e.target.value)}
                        placeholder={`Min ₹${minimum}`}
                        onWheel={(e) => e.target.blur()}
                        className={belowMin ? "border-red-500 focus-visible:ring-red-500" : undefined}
                        aria-invalid={belowMin || undefined}
                        data-testid={`pricing-${courtType}-${slot}`}
                      />
                      {belowMin ? (
                        <p className="text-2xs text-red-600 mt-0.5">Must be at least ₹{minimum}</p>
                      ) : (
                        <p className="text-2xs text-muted-foreground mt-0.5">Min ₹{minimum}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
          <Button type="button" onClick={save} disabled={saving || hasInvalidPricing()} className="bg-accent hover:bg-accent/90 font-bold">Save profile</Button>
        </CardContent>
      </Card>
    </div>
  );
}

// Rows saved before the Time Slot picker existed carry literal clock times
// (start_time "09:03", end_time "18:03") instead of one of
// TIME_OF_DAY_OPTIONS — show both ends rather than a bare "09:03".
function formatSlotTime(slot) {
  if (!slot.start_time) return "Full day";
  if (!TIME_OF_DAY_OPTIONS.includes(slot.start_time) && slot.end_time) return `${slot.start_time} – ${slot.end_time}`;
  return slot.start_time;
}

const EMPTY_SLOT_FORM = { kind: "recurring_weekly", dayOfWeek: 0, date: "", courtId: "", timeSlot: "" };

/* "Visible to clients?" — practice.client_visibility's read-back of the same
   gates client search applies (approval, profile courts, slot pricing).
   Exists because "Availability added" alone said nothing about whether a
   client could actually find this counsel: a saved slot can match while the
   profile itself is still excluded. Failing blocking checks first. */
export function ClientVisibilityCard({ visibility }) {
  if (!visibility) return null;
  const failing = visibility.checks
    .filter((c) => !c.ok)
    .sort((a, b) => (a.severity === "blocking" ? 0 : 1) - (b.severity === "blocking" ? 0 : 1));
  const allClear = visibility.visible && failing.length === 0;
  return (
    <Card className="dashboard-card border-none" data-testid="client-visibility-card">
      <CardContent className="p-5">
        <div className="flex items-start gap-3">
          {allClear
            ? <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            : visibility.visible
              ? <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              : <XCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />}
          <div className="min-w-0">
            <div className="font-display font-bold" data-testid="client-visibility-status">
              {allClear
                ? "Clients can find you"
                : visibility.visible ? "Clients can find you, with gaps" : "Clients can't find you yet"}
            </div>
            {failing.length > 0 && (
              <ul className="mt-2 space-y-1.5">
                {failing.map((c) => (
                  <li key={c.key} className="text-sm flex gap-2" data-testid={`client-visibility-${c.key}`}>
                    <span className={`mt-2 w-1.5 h-1.5 rounded-full shrink-0 ${c.severity === "blocking" ? "bg-red-500" : "bg-amber-500"}`} />
                    <span>{c.message}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function AvailabilityTab() {
  const [slots, setSlots] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const [form, setForm] = useState(EMPTY_SLOT_FORM);
  // slot_id being edited, or null when the card is adding a new slot.
  const [editingId, setEditingId] = useState(null);
  const [savingSlot, setSavingSlot] = useState(false);
  const [removingId, setRemovingId] = useState(null);
  const [visibility, setVisibility] = useState(null);
  const { kind, dayOfWeek, date, courtId, timeSlot } = form;
  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }));
  const today = resolveDateBound("today");

  // The visibility check is advisory: if it fails to load, the card just
  // stays hidden rather than blocking the tab.
  const load = () => {
    getPracticeVisibility().then(setVisibility).catch(() => setVisibility(null));
    return listAvailabilitySlots()
      .then((rows) => { setSlots(rows); setLoadError(false); })
      .catch(() => { setSlots([]); setLoadError(true); });
  };
  useEffect(() => { load(); }, []);

  // Required fields are Kind (always has a value — the Select has no blank
  // state), Day of week or Date depending on Kind, and Time Slot (see
  // practice.py's _validated_slot_fields, which enforces the same rules plus
  // a real, not-yet-passed date). Court stays the one optional field. Also
  // drives the submit button's faded/bright state.
  const dayOrDateFilled = kind === "recurring_weekly" ? dayOfWeek != null : !!date;
  const dateInPast = kind !== "recurring_weekly" && !!date && date < today;
  const isFormReady = dayOrDateFilled && !dateInPast && !!timeSlot;

  const resetForm = () => {
    setForm(EMPTY_SLOT_FORM);
    setEditingId(null);
  };

  const startEdit = (slot) => {
    setEditingId(slot.slot_id);
    setForm({
      kind: slot.kind,
      dayOfWeek: slot.day_of_week ?? 0,
      date: slot.date || "",
      // A legacy free-text court can't be re-saved; it has to be picked again.
      courtId: slot.court_known === false ? "" : slot.court_id || "",
      // A legacy clock-time row has no matching option — force an explicit pick.
      timeSlot: TIME_OF_DAY_OPTIONS.includes(slot.start_time) ? slot.start_time : "",
    });
  };

  const submit = async () => {
    if (!isFormReady) {
      if (!dayOrDateFilled) toast.error("Pick a day or date first");
      else if (dateInPast) toast.error("That date has already passed. Pick today or a future date.");
      else toast.error("Select a time slot");
      return;
    }
    const payload = {
      kind,
      day_of_week: kind === "recurring_weekly" ? dayOfWeek : undefined,
      date: kind !== "recurring_weekly" ? date : undefined,
      court_id: courtId || undefined,
      start_time: timeSlot,
    };
    setSavingSlot(true);
    try {
      if (editingId) {
        await updateAvailabilitySlot(editingId, payload);
        toast.success("Availability updated");
        resetForm();
      } else {
        await addAvailabilitySlot(payload);
        toast.success("Availability added");
        setField("timeSlot", ""); // force a fresh, explicit pick for the next slot rather than resubmitting the same one
      }
      load();
    } catch (err) {
      toast.error(getErrorMessage(err, editingId ? "Could not update slot" : "Could not add slot"));
    } finally {
      setSavingSlot(false);
    }
  };

  const remove = async (slotId) => {
    setRemovingId(slotId);
    try {
      await removeAvailabilitySlot(slotId);
      toast.success("Availability removed");
      if (editingId === slotId) resetForm();
      load();
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not remove slot"));
    } finally {
      setRemovingId(null);
    }
  };

  // Current slots first, then dated ones that have already passed (they no
  // longer affect search, but stay visible so they can be cleaned up).
  const orderedSlots = slots && [...slots.filter((s) => !s.is_past), ...slots.filter((s) => s.is_past)];

  return (
    <div className="space-y-4">
      <ClientVisibilityCard visibility={visibility} />
      <Card className="dashboard-card border-none">
        <CardContent className="p-5">
          <div className="font-display font-bold mb-3">{editingId ? "Edit availability" : "Add availability"}</div>
          <div className="grid sm:grid-cols-2 gap-3 mb-3">
            <div>
              <Label>Kind *</Label>
              <Select value={kind} onValueChange={(v) => setField("kind", v)}>
                <SelectTrigger data-testid="availability-kind"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {KINDS.map((k) => <SelectItem key={k.value} value={k.value}>{k.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {kind === "recurring_weekly" ? (
              <div>
                <Label>Day of week *</Label>
                <Select value={String(dayOfWeek)} onValueChange={(v) => setField("dayOfWeek", Number(v))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {DAYS.map((d, i) => <SelectItem key={d} value={String(i)}>{d}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            ) : (
              <div>
                <Label>Date *</Label>
                <Input
                  type="date" value={date} min={today} onChange={(e) => setField("date", e.target.value)}
                  aria-invalid={dateInPast || undefined}
                  className={dateInPast ? "border-red-500 focus-visible:ring-red-500" : undefined}
                  data-testid="availability-date"
                />
                {dateInPast && <p className="text-2xs text-red-600 mt-0.5">This date has already passed</p>}
              </div>
            )}
            <div>
              {/* Single court: picking another replaces it. */}
              <CourtPicker
                label="Court (optional)"
                value={courtId ? [courtId] : []}
                onChange={(ids) => setField("courtId", ids[ids.length - 1] || "")}
                placeholder="Search a court, e.g. Delhi High Court"
                hint="Clients search by the courts on your profile. Add this court under Profile → Courts too."
                testId="availability-court-search"
              />
            </div>
            <div>
              <Label>Time Slot *</Label>
              <Select value={timeSlot || undefined} onValueChange={(v) => setField("timeSlot", v)}>
                <SelectTrigger data-testid="availability-time-slot"><SelectValue placeholder="Select a time slot" /></SelectTrigger>
                <SelectContent>
                  {TIME_OF_DAY_OPTIONS.map((opt) => <SelectItem key={opt} value={opt}>{opt}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button" onClick={submit} disabled={savingSlot}
              className={isFormReady
                ? "bg-accent hover:bg-accent/90 font-bold"
                : "bg-accent/50 hover:bg-accent/60 font-bold"}
              data-testid="availability-submit"
            >
              {savingSlot
                ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
                : !editingId && <Plus className="w-4 h-4 mr-1.5" />}
              {editingId ? "Save changes" : "Add"}
            </Button>
            {editingId && (
              <Button type="button" variant="outline" onClick={resetForm} disabled={savingSlot} data-testid="availability-cancel-edit">
                Cancel
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="rounded-xl border bg-white overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Kind</TableHead>
              <TableHead>When</TableHead>
              <TableHead>Court</TableHead>
              <TableHead>Time</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {slots === null && <TableLoading colSpan={5} />}
            {slots?.length === 0 && (
              <TableEmpty colSpan={5}>
                {loadError ? "Couldn't load your availability. Refresh the page to try again." : "No availability set yet"}
              </TableEmpty>
            )}
            {orderedSlots?.map((s) => (
              <TableRow
                key={s.slot_id}
                className={`${s.is_past ? "opacity-60" : ""} ${editingId === s.slot_id ? "bg-accent/5" : ""}`}
                data-testid={`availability-row-${s.slot_id}`}
              >
                <TableCell><Badge variant="outline" className="text-2xs uppercase">{s.kind.replace(/_/g, " ")}</Badge></TableCell>
                <TableCell>
                  {s.kind === "recurring_weekly" ? DAYS[s.day_of_week] : s.date}
                  {s.is_past && <Badge variant="outline" className="ml-2 text-2xs">Past</Badge>}
                </TableCell>
                <TableCell>
                  {s.court_name || s.court_id || "Any"}
                  {s.court_known === false && <span className="block text-2xs text-amber-700">Not a recognized court, edit to re-pick</span>}
                </TableCell>
                <TableCell>{formatSlotTime(s)}</TableCell>
                <TableCell>
                  <div className="flex items-center justify-end gap-3">
                    {!s.is_past && (
                      <button
                        type="button" onClick={() => startEdit(s)} aria-label="Edit availability"
                        className="text-muted-foreground hover:text-accent" data-testid={`availability-edit-${s.slot_id}`}
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                    )}
                    <button
                      type="button" onClick={() => remove(s.slot_id)} disabled={removingId === s.slot_id}
                      aria-label="Remove availability" className="text-muted-foreground hover:text-red-600 disabled:opacity-50"
                      data-testid={`availability-remove-${s.slot_id}`}
                    >
                      {removingId === s.slot_id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                    </button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function PerformanceTab() {
  const [perf, setPerf] = useState(null);
  useEffect(() => { getPracticePerformance().then(setPerf); }, []);
  if (!perf) return <Loading />;

  const stats = [
    { label: "Rating", value: perf.rating || "—", icon: Star, color: "bg-amber-100 text-amber-700" },
    { label: "Cases Completed", value: perf.cases_completed, icon: CheckCircle2, color: "bg-emerald-100 text-emerald-700" },
    { label: "Upcoming Hearings", value: perf.upcoming_hearings, icon: Clock, color: "bg-accent/10 text-accent" },
    { label: "Pending Requests", value: perf.pending_requests, icon: Briefcase, color: "bg-blue-100 text-blue-700" },
  ];
  return <StatGrid stats={stats} />;
}

export function HearingsTab({ initialActiveId = null }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [hearings, setHearings] = useState(null);
  const [activeId, setActiveId] = useState(initialActiveId);

  const load = () => listHearingRequests().then(setHearings);
  useEffect(() => { load(); }, []);

  // Negotiation Module: a hearing targeted at this advocate is invisible
  // everywhere else until it reaches "broadcast" (post-payment) — this is
  // the one place the pending-negotiation window (see hearings.py's
  // list_hearing_requests) actually surfaces to them.
  const negotiating = hearings?.filter((h) => h.target_advocate_id === user?.user_id
    && ["requested", "payment_pending"].includes(h.status)) || [];
  const open = hearings?.filter((h) => h.status === "broadcast" && h.requesting_user_id !== user?.user_id) || [];
  const mine = hearings?.filter((h) => h.proxy_counsel_user_id === user?.user_id) || [];
  // Assigned hearings run the full lifecycle (including cancel/expire), so
  // unlike Negotiation/Open Requests above this needs its own Active/
  // Completed/Cancelled split rather than one flat list.
  const mineTabs = {
    active: mine.filter(isHearingActive),
    completed: mine.filter((h) => COMPLETED_HEARING_STATUSES.includes(h.status)),
    cancelled: mine.filter((h) => CLOSED_HEARING_STATUSES.includes(h.status)),
  };

  const renderCard = (h, onClick) => (
    <Card key={h.hearing_id} className="dashboard-card border-none cursor-pointer hover:shadow-md transition-shadow" onClick={onClick}>
      <CardContent className="p-4">
        {/* flex-wrap + truncate: same fix as CounselHiringPage's "My
            Requests" cards — a long status label (e.g. "Waiting for Hiring
            Advocate Payment") with nowhere to wrap on a no-wrap row either
            overflowed past the screen edge or squeezed the title down to a
            couple of characters. */}
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
          <div className="min-w-0 flex-1">
            <div className="font-display font-bold text-sm truncate">{h.court_id}</div>
            <div className="text-xs text-muted-foreground">{h.hearing_date} {h.fee ? `· ₹${h.fee}` : ""}</div>
          </div>
          <Badge className={`${HEARING_STATUS_BADGE_COLOR[h.status] || ""} border-0 font-bold uppercase text-2xs ml-auto`}>
            {roleAwareStatusLabel(h, getViewerRole(h, user?.user_id))}
          </Badge>
        </div>
        <HearingActivityPreview hearing={h} />
      </CardContent>
    </Card>
  );

  return (
    <div className="space-y-6">
      {/* Pending Offers — hiring-flow UX rewrite: a counsel should never have
          to hunt through notifications to find work waiting on them. This is
          the one place a targeted, pre-payment hearing (see hearings.py's
          list_hearing_requests — invisible everywhere else until "broadcast")
          actually surfaces in their own workspace. Each card shows only what's
          needed to recognize the request at a glance; the actual Accept/
          Reject/Negotiate actions live on the (also redesigned) Negotiation
          page — one "Respond to Offer" CTA here, not a second copy of those
          three buttons competing for space on this list. */}
      {!!negotiating.length && (
        <div>
          <div className="font-display font-bold mb-2">Pending Offers</div>
          <p className="text-xs text-muted-foreground mb-3">A client has requested you directly — respond to move forward.</p>
          <div className="grid sm:grid-cols-2 gap-3">
            {negotiating.map((h) => (
              <Card key={h.hearing_id} className="border-l-4 border-l-accent shadow-sm" data-testid={`pending-offer-${h.hearing_id}`}>
                <CardContent className="p-4">
                  <div className="font-display font-bold text-sm truncate">{h.request_details?.common?.case_title || h.court_id}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">{h.request_details?.common?.court_name || h.court_id} · {h.hearing_date}</div>
                  {/* A fixed-price offer has no fee until Accept — show the
                      listed rate it will lock (hearings._attach_listed_rates). */}
                  {(h.fee ?? h.listed_rate) != null && (
                    <div className="text-lg font-display font-bold mt-2">{formatINR(h.fee ?? h.listed_rate)}</div>
                  )}
                  <Button
                    type="button" size="sm" className="w-full font-bold bg-accent hover:bg-accent/90 mt-3"
                    onClick={() => (counselRespondsViaNegotiation(h)
                      ? navigate(`/hearing-requests/${h.hearing_id}/negotiate`)
                      : setActiveId(h.hearing_id))}
                    data-testid={`respond-to-offer-${h.hearing_id}`}
                  >
                    Respond to Offer <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
      <div>
        <div className="font-display font-bold mb-2">Open Requests</div>
        {hearings === null && <Loading size="sm" />}
        {hearings && open.length === 0 && <p className="text-sm text-muted-foreground">No open requests right now.</p>}
        <div className="space-y-2">{open.map((h) => renderCard(h, () => setActiveId(h.hearing_id)))}</div>
      </div>
      <div>
        <div className="font-display font-bold mb-2">My Hearings</div>
        {hearings === null && <Loading size="sm" />}
        {hearings && mine.length === 0 && <p className="text-sm text-muted-foreground">Nothing accepted yet.</p>}
        {hearings && mine.length > 0 && (
          <Tabs defaultValue="active">
            <TabsList data-testid="my-hearings-tabs">
              {Object.entries(mineTabs).map(([key, list]) => (
                <TabsTrigger key={key} value={key} data-testid={`tab-my-${key}`}>
                  {HEARING_TAB_LABELS[key]} ({list.length})
                </TabsTrigger>
              ))}
            </TabsList>
            {Object.entries(mineTabs).map(([key, list]) => (
              <TabsContent value={key} key={key} className="mt-3 space-y-2">
                {list.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-2">No {HEARING_TAB_LABELS[key].toLowerCase()} hearings.</p>
                ) : list.map((h) => renderCard(h, () => setActiveId(h.hearing_id)))}
              </TabsContent>
            ))}
          </Tabs>
        )}
      </div>
      <HearingDetailDialog hearingId={activeId} open={!!activeId} onOpenChange={(v) => !v && setActiveId(null)} onChanged={load} />
    </div>
  );
}

export default function Practice() {
  const [profile, setProfile] = useState(null);
  // A hearing to open on arrival (NegotiationModule sends a counsel here for
  // a non-negotiable offer) — read once, then dropped from history so a
  // refresh doesn't reopen it.
  const location = useLocation();
  const navigate = useNavigate();
  const [openHearingId] = useState(() => location.state?.openHearingId || null);
  useEffect(() => {
    if (location.state?.openHearingId) navigate(location.pathname, { replace: true, state: null });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { getPracticeProfile().then(setProfile); }, []);

  return (
    <PageContainer className="max-w-4xl">
      <PageHeader eyebrow="My Practice" eyebrowIcon={Briefcase} title="Your practice, in one place" />
      <Tabs defaultValue={openHearingId ? "hearings" : "profile"} className="mt-6">
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="availability">Availability</TabsTrigger>
          <TabsTrigger value="hearings">Hearings</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
        </TabsList>
        <TabsContent value="profile" className="mt-4">
          {profile ? <ProfileTab profile={profile} onSaved={setProfile} /> : <Loading />}
        </TabsContent>
        <TabsContent value="availability" className="mt-4">
          <AvailabilityTab />
        </TabsContent>
        <TabsContent value="hearings" className="mt-4">
          <HearingsTab initialActiveId={openHearingId} />
        </TabsContent>
        <TabsContent value="performance" className="mt-4">
          <PerformanceTab />
        </TabsContent>
      </Tabs>
    </PageContainer>
  );
}
