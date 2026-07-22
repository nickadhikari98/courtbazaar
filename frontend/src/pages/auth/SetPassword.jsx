import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, setToken } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Loader2, Eye, EyeOff } from "lucide-react";
import Logo from "@/components/shared/Logo";

/* Landing page for the one-time link emailed by the Lead->Professional
   bridge (leads.py's _activate_professional / notifications.tmpl_set_password)
   when an approved application creates a brand-new account. */
export default function SetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const confirmMismatch = confirm.length > 0 && password !== confirm;

  const submit = async (e) => {
    e.preventDefault();
    if (!token) {
      toast.error("This link is missing its token — please use the link from your email.");
      return;
    }
    if (password.length < 8) {
      toast.error("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      toast.error("Passwords don't match.");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post("/auth/set-password", { token, password });
      setToken(data.token);
      await refresh();
      toast.success("Password set. Welcome to CourtBazaar™!");
      navigate("/dashboard");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not set your password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <CardContent className="p-8">
          <Logo size="lg" className="mb-6 justify-center" data-testid="set-password-logo" />
          <h1 className="font-display font-black text-2xl tracking-tighter text-center">Set your password</h1>
          <p className="text-sm text-muted-foreground text-center mt-1 mb-6">
            Your application was approved — choose a password to log in.
          </p>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <Label htmlFor="password">New password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute inset-y-0 right-0 flex items-center px-3 text-muted-foreground hover:text-foreground"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  data-testid="set-password-toggle"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <div>
              <Label htmlFor="confirm">Confirm password</Label>
              <div className="relative">
                <Input
                  id="confirm"
                  type={showConfirm ? "text" : "password"}
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                  minLength={8}
                  className={`pr-10 ${confirmMismatch ? "border-destructive focus-visible:ring-destructive" : ""}`}
                  aria-invalid={confirmMismatch}
                  data-testid="set-password-confirm-input"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirm((v) => !v)}
                  className="absolute inset-y-0 right-0 flex items-center px-3 text-muted-foreground hover:text-foreground"
                  aria-label={showConfirm ? "Hide password" : "Show password"}
                  data-testid="set-password-confirm-toggle"
                >
                  {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {confirmMismatch && (
                <p className="text-xs text-destructive mt-1" data-testid="set-password-mismatch-error">
                  Passwords don't match.
                </p>
              )}
            </div>
            <Button type="submit" disabled={loading || confirmMismatch} className="w-full bg-accent hover:bg-accent/90 font-bold">
              {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
              Set password &amp; log in
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
