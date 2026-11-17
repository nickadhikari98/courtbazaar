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
