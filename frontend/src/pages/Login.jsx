import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "sonner";
import { Scale, ArrowRight, Phone, Mail, Loader2 } from "lucide-react";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, otpRequest, otpVerify, googleLogin } = useAuth();
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState("advocate@demo.in");
  const [password, setPassword] = useState("Advocate@123");
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [otpSent, setOtpSent] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const u = await login(email, password);
      toast.success(`Welcome back, ${u.name}`);
      navigate(u.role === "admin" ? "/admin" : u.role === "vendor" ? "/vendor" : "/dashboard");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Login failed");
    } finally { setLoading(false); }
  };

  const handleOtpSend = async () => {
    if (!phone.match(/^\d{10}$/)) {
      toast.error("Enter a valid 10-digit phone number");
      return;
    }
    setLoading(true);
    try {
      await otpRequest(phone);
      setOtpSent(true);
      toast.success("OTP sent (use 123456 for demo)");
    } catch (e) {
      toast.error("Could not send OTP");
    } finally { setLoading(false); }
  };

  const handleOtpVerify = async () => {
    setLoading(true);
    try {
      const u = await otpVerify(phone, otp);
      toast.success(`Welcome, ${u.name}`);
      navigate("/dashboard");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Invalid OTP");
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-background grid grid-cols-1 lg:grid-cols-2">
      <div className="hidden lg:block relative bg-primary overflow-hidden">
        <div className="absolute inset-0 cb-grain opacity-30"></div>
        <img src="https://images.unsplash.com/photo-1593115057322-e94b77572f20?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200" className="absolute inset-0 w-full h-full object-cover opacity-30" alt="" />
        <div className="relative h-full p-12 flex flex-col justify-between text-white">
          <Link to="/" className="flex items-center gap-2.5" data-testid="login-logo">
            <div className="w-10 h-10 bg-accent rounded-lg flex items-center justify-center">
              <Scale className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="font-display font-black text-xl tracking-tight leading-none">CourtBazaar</div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-white/70 font-bold mt-0.5">India</div>
            </div>
          </Link>
          <div className="space-y-6 max-w-md">
            <h1 className="font-display font-black text-5xl tracking-tighter leading-[0.95]">
              India's largest legal services marketplace.
            </h1>
            <p className="text-white/70 text-lg font-medium">
              Photocopy. Print. E-File. Notarize. Bind. Deliver. Every court chore — one login.
            </p>
            <div className="flex items-center gap-4 text-sm text-white/80 font-semibold">
              <div>1,200+ vendors</div>
              <div className="w-1 h-1 bg-white/40 rounded-full"></div>
              <div>850+ courts</div>
              <div className="w-1 h-1 bg-white/40 rounded-full"></div>
              <div>28 states</div>
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-center p-6 lg:p-12">
        <Card className="w-full max-w-md border-none shadow-none">
          <CardContent className="p-0">
            <div className="mb-8">
              <div className="cb-overline text-accent">Welcome back</div>
              <h2 className="font-display font-black text-4xl mt-2 tracking-tighter">Sign in to CourtBazaar</h2>
              <p className="text-muted-foreground mt-2 font-medium">No account? <Link to="/register" className="text-accent font-bold hover:underline" data-testid="login-go-register">Create one</Link></p>
            </div>

            <Tabs defaultValue="email">
              <TabsList className="grid w-full grid-cols-2 mb-6" data-testid="login-tabs">
                <TabsTrigger value="email" data-testid="login-tab-email"><Mail className="w-4 h-4 mr-2" /> Email</TabsTrigger>
                <TabsTrigger value="phone" data-testid="login-tab-phone"><Phone className="w-4 h-4 mr-2" /> Phone OTP</TabsTrigger>
              </TabsList>

              <TabsContent value="email">
                <form onSubmit={handleLogin} className="space-y-4">
                  <div>
                    <Label htmlFor="email">Email</Label>
                    <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required data-testid="login-email-input" />
                  </div>
                  <div>
                    <Label htmlFor="password">Password</Label>
                    <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required data-testid="login-password-input" />
                  </div>
                  <Button type="submit" disabled={loading} className="w-full bg-primary hover:bg-primary/90 h-12 font-bold" data-testid="login-submit-btn">
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Sign in <ArrowRight className="w-4 h-4 ml-2" /></>}
                  </Button>
                </form>
                <div className="mt-4 text-xs bg-secondary rounded-lg p-3 space-y-1">
                  <div className="font-bold cb-overline text-foreground/70">Demo accounts</div>
                  <div className="font-mono">advocate@demo.in · Advocate@123</div>
                  <div className="font-mono">vendor@demo.in · Vendor@123</div>
                  <div className="font-mono">admin@courtbazaar.in · Admin@123</div>
                </div>
              </TabsContent>

              <TabsContent value="phone">
                {!otpSent ? (
                  <div className="space-y-4">
                    <div>
                      <Label>Phone Number</Label>
                      <div className="flex gap-2">
                        <div className="px-3 flex items-center bg-secondary rounded-md text-sm font-semibold">+91</div>
                        <Input value={phone} onChange={(e) => setPhone(e.target.value.replace(/\D/g, "").slice(0, 10))} placeholder="9876543210" data-testid="login-phone-input" />
                      </div>
                    </div>
                    <Button onClick={handleOtpSend} disabled={loading} className="w-full bg-primary h-12 font-bold" data-testid="login-otp-send-btn">
                      {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Send OTP"}
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div>
                      <Label>Enter OTP sent to +91 {phone}</Label>
                      <div className="mt-2 flex justify-center">
                        <InputOTP maxLength={6} value={otp} onChange={setOtp} data-testid="login-otp-input">
                          <InputOTPGroup>
                            {[0,1,2,3,4,5].map(i => <InputOTPSlot key={i} index={i} />)}
                          </InputOTPGroup>
                        </InputOTP>
                      </div>
                      <div className="text-center mt-2 text-xs text-muted-foreground">Use <b className="text-accent">123456</b> for demo</div>
                    </div>
                    <Button onClick={handleOtpVerify} disabled={loading || otp.length < 6} className="w-full bg-primary h-12 font-bold" data-testid="login-otp-verify-btn">
                      {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Verify & Continue"}
                    </Button>
                  </div>
                )}
              </TabsContent>
            </Tabs>

            <div className="relative my-6">
              <div className="cb-divider"></div>
              <span className="absolute inset-0 flex items-center justify-center text-xs uppercase tracking-widest text-muted-foreground"><span className="bg-background px-3 font-bold">or</span></span>
            </div>

            <Button variant="outline" className="w-full h-12 font-bold border-2" onClick={() => googleLogin("advocate")} data-testid="login-google-btn">
              <svg className="w-4 h-4 mr-2" viewBox="0 0 24 24"><path fill="#4285f4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34a853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#fbbc05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#ea4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
              Continue with Google
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
