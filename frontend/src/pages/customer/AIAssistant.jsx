import React, { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Send, Sparkles, Loader2, Scale, User } from "lucide-react";

const SUGGESTIONS = [
  "What docs needed for filing a writ petition in Delhi HC?",
  "Defect check: my paper book has 412 pages, B&W, spiral bound. Any issues?",
  "Calculate court fee for property suit valued ₹50 lakh in Mumbai",
  "Best service combo for filing 5 affidavits at Patiala House Court?",
];

export default function AIAssistant() {
  const [sessionId] = useState(() => `sess_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`);
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const send = async (text) => {
    const content = text || input;
    if (!content.trim() || loading) return;
    setMsgs(prev => [...prev, { role: "user", text: content }]);
    setInput("");
    setLoading(true);
    try {
      const { data } = await api.post("/ai/chat", { session_id: sessionId, message: content });
      setMsgs(prev => [...prev, { role: "assistant", text: data.reply }]);
    } catch (e) {
      toast.error("AI is unavailable. Try again.");
    } finally { setLoading(false); }
  };

  return (
    // Intentionally not PageContainer: this is a full-viewport-height flex
    // chat column (h-[calc(100vh-64px)] flex flex-col), not a simple padded
    // content wrapper — a structurally different layout need, not a missed
    // migration. See DESIGN_SYSTEM_AUDIT.md §5.
    <div className="p-6 lg:p-10 max-w-4xl mx-auto h-[calc(100vh-64px)] flex flex-col">
      <div className="mb-5">
        <div className="cb-overline text-accent flex items-center gap-2"><Sparkles className="w-3 h-3" /> AI Legal Assistant · Claude Sonnet</div>
        <h1 className="font-display font-black text-3xl tracking-tighter mt-1">Ask anything about Indian courts.</h1>
      </div>

      <Card className="dashboard-card border-none flex-1 flex flex-col overflow-hidden">
        <CardContent className="flex-1 overflow-y-auto p-6 space-y-4" data-testid="ai-messages">
          {msgs.length === 0 && (
            <div className="text-center py-10">
              <div className="w-16 h-16 mx-auto bg-accent/10 rounded-2xl flex items-center justify-center mb-4">
                <Scale className="w-8 h-8 text-accent" />
              </div>
              <div className="font-display font-bold text-xl">How can I help, advocate?</div>
              <p className="text-muted-foreground mt-1 text-sm font-medium">Court selection, filing checklists, defect checks & more.</p>
              <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-2xl mx-auto">
                {SUGGESTIONS.map((s, i) => (
                  <button key={i} onClick={() => send(s)} className="text-left p-3 bg-secondary hover:bg-secondary/70 rounded-lg text-sm font-semibold transition-colors" data-testid={`ai-suggestion-${i}`}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`} data-testid={`ai-msg-${m.role}-${i}`}>
              <div className={`w-8 h-8 rounded-lg shrink-0 flex items-center justify-center ${m.role === 'user' ? 'bg-primary text-white' : 'bg-accent text-white'}`}>
                {m.role === 'user' ? <User className="w-4 h-4" /> : <Sparkles className="w-4 h-4" />}
              </div>
              <div className={`max-w-[80%] rounded-2xl p-4 ${m.role === 'user' ? 'bg-primary text-white' : 'bg-secondary text-foreground'}`}>
                <div className="text-sm whitespace-pre-wrap font-medium leading-relaxed">{m.text}</div>
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex gap-3" data-testid="ai-loading">
              <div className="w-8 h-8 rounded-lg bg-accent text-white flex items-center justify-center"><Sparkles className="w-4 h-4" /></div>
              <div className="bg-secondary rounded-2xl p-4 flex gap-1.5">
                <div className="w-2 h-2 bg-accent rounded-full animate-bounce" style={{animationDelay: '0ms'}}></div>
                <div className="w-2 h-2 bg-accent rounded-full animate-bounce" style={{animationDelay: '150ms'}}></div>
                <div className="w-2 h-2 bg-accent rounded-full animate-bounce" style={{animationDelay: '300ms'}}></div>
              </div>
            </div>
          )}
          <div ref={endRef}></div>
        </CardContent>
        <div className="border-t border-border p-4 flex gap-2">
          <Input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send()} placeholder="Ask about courts, filings, defects, pricing…" className="flex-1" data-testid="ai-input" disabled={loading} />
          <Button onClick={() => send()} disabled={loading || !input.trim()} className="bg-accent hover:bg-accent/90 font-bold px-5" data-testid="ai-send-btn">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </Button>
        </div>
      </Card>
    </div>
  );
}
