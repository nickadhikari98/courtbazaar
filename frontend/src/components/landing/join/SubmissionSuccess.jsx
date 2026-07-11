import React from "react";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function SubmissionSuccess({ onBackToHome }) {
  return (
    <div className="flex flex-col items-center text-center py-6 px-2">
      <div className="w-16 h-16 rounded-full bg-emerald-50 flex items-center justify-center mb-5">
        <CheckCircle2 className="w-9 h-9 text-emerald-500" strokeWidth={1.75} />
      </div>
      <h3 className="font-display font-bold text-2xl mb-2">Thank You!</h3>
      <p className="text-sm text-muted-foreground max-w-sm leading-relaxed">
        Thank you for submitting your application. Our team will review your details and contact you shortly.
      </p>
      <p className="text-sm text-muted-foreground max-w-sm leading-relaxed mt-2">
        We've sent a confirmation email to your registered address — please check your inbox (and spam folder) to verify it.
      </p>
      <Button
        type="button"
        onClick={onBackToHome}
        className="bg-accent hover:bg-accent/90 text-white font-bold px-8 mt-6"
      >
        Back to Home
      </Button>
    </div>
  );
}
