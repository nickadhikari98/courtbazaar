import React from "react";
import { X, ArrowLeft, ArrowRight } from "lucide-react";

export default function TourTooltip({
  backProps, closeProps, index, isLastStep, primaryProps, size, skipProps, step, tooltipProps,
}) {
  return (
    <div
      {...tooltipProps}
      className="relative bg-white rounded-2xl p-6 w-[320px] max-w-[90vw]"
      style={{ boxShadow: "0 24px 60px -12px rgba(15, 23, 42, 0.35), 0 8px 24px -8px rgba(15, 23, 42, 0.2)" }}
    >
      <button
        {...closeProps}
        aria-label="Skip Tour"
        className="absolute top-4 right-4 text-slate-300 hover:text-slate-500 transition-colors"
      >
        <X className="w-4 h-4" />
      </button>

      <span className="inline-block text-[11px] font-bold uppercase tracking-wide text-accent mb-2">
        {index + 1} of {size}
      </span>

      {step.title && (
        <h3 className="font-display font-bold text-lg text-foreground mb-1.5 pr-5">{step.title}</h3>
      )}
      <div className="text-sm text-muted-foreground leading-relaxed">{step.content}</div>

      <div className="flex items-center justify-between mt-5 pt-4 border-t border-slate-100">
        <button
          {...skipProps}
          className="text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
        >
          Skip Tour
        </button>
        <div className="flex items-center gap-2">
          {index > 0 && (
            <button
              {...backProps}
              className="inline-flex items-center gap-1 text-xs font-bold text-foreground border border-slate-200 rounded-md px-3 py-2 hover:bg-slate-50 transition-colors duration-200"
            >
              <ArrowLeft className="w-3.5 h-3.5" /> Previous
            </button>
          )}
          <button
            {...primaryProps}
            className="inline-flex items-center gap-1 text-xs font-bold text-white bg-accent hover:bg-accent/90 rounded-md px-4 py-2 transition-colors duration-200"
          >
            {isLastStep ? "Finish" : "Next"} {!isLastStep && <ArrowRight className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>
    </div>
  );
}
