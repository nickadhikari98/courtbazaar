/* GET /ai/usage -> what the header pill, sidebar block and settings show.
   Only numbers the endpoint returned (messages left is limit - used); null
   when there is nothing trustworthy to show. */
export function resetTime(iso) {
  const d = new Date(iso);
  return typeof iso === "string" && !Number.isNaN(d.getTime())
    ? d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : null;
}

const num = (v) => typeof v === "number" && Number.isFinite(v);

export function formatUsage(u) {
  if (!u || typeof u !== "object" || Array.isArray(u)) return null;
  const reset = resetTime(u.resets_at);
  const resets = reset ? `Resets at ${reset}.` : "";
  if (num(u.messages_limit) && num(u.messages_used)) {
    const left = Math.max(0, u.messages_limit - u.messages_used);
    return {
      pill: `${left} left`, reset, label: "Today's questions", used: u.messages_used, limit: u.messages_limit,
      detail: `${u.messages_used} of ${u.messages_limit} questions used today. ${resets}`.trim(),
    };
  }
  if (num(u.tokens_limit) && num(u.tokens_used)) {
    return {
      pill: "Unlimited", reset, label: "Today's tokens", used: u.tokens_used, limit: u.tokens_limit,
      detail: `Unlimited questions. ${u.tokens_used.toLocaleString()} of ${u.tokens_limit.toLocaleString()} tokens used today. ${resets}`.trim(),
    };
  }
  return null;
}

/* The muted line under the composer as the daily limit gets close, from the
   endpoint's numbers only (left = limit - used). Guests from 2 left, free
   users from 5 left, paid users at 90% of the token cap; none at the limit
   itself (the limit card takes over). */
export function usageReminder(u) {
  if (!u || typeof u !== "object") return null;
  if (num(u.messages_limit) && num(u.messages_used)) {
    const left = u.messages_limit - u.messages_used;
    if (left < 1) return null;
    if (u.plan === "guest") {
      if (left === 1) return "1 question left today. Register free for 30 a day.";
      return left === 2 ? "2 free questions left today." : null;
    }
    if (left === 1) return "1 question left today.";
    return left <= 5 ? `${left} questions left today.` : null;
  }
  if (u.plan === "paid" && num(u.tokens_limit) && num(u.tokens_used) && u.tokens_limit > 0
      && u.tokens_used >= 0.9 * u.tokens_limit && u.tokens_used < u.tokens_limit) {
    return "You're near today's AI usage allowance. It resets at midnight IST.";
  }
  return null;
}
