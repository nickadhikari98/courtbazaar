import React, { useState } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import RoleForm from "./RoleForm";

export default function RoleSelectModal({
  open,
  onOpenChange,
  heading = "Select Your Role",
  subheading,
  roles = [],
  forms = {},
}) {
  const [selected, setSelected] = useState(null);

  const handleOpenChange = (next) => {
    onOpenChange(next);
    if (!next) {
      setTimeout(() => setSelected(null), 200);
    }
  };

  const activeRole = roles.find((r) => r.key === selected);
  const activeForm = selected ? forms[selected] : null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
        {!selected ? (
          <>
            <DialogHeader>
              <DialogTitle className="font-display text-xl">{heading}</DialogTitle>
              {subheading && <DialogDescription>{subheading}</DialogDescription>}
            </DialogHeader>
            <div className={`grid gap-4 pt-2 ${roles.length === 2 ? "sm:grid-cols-2" : "sm:grid-cols-3"}`}>
              {roles.map((role) => (
                <button
                  key={role.key}
                  type="button"
                  onClick={() => setSelected(role.key)}
                  className="group relative flex flex-col items-center text-center gap-3 rounded-xl border-2 border-slate-200 p-6 transition-all duration-200 hover:border-accent hover:shadow-lg hover:-translate-y-0.5"
                >
                  <div className="w-16 h-16 rounded-full bg-slate-50 group-hover:bg-accent/10 flex items-center justify-center transition-colors overflow-hidden">
                    {role.image ? (
                      <img src={role.image} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <role.icon className="w-7 h-7 text-primary group-hover:text-accent transition-colors" strokeWidth={1.75} />
                    )}
                  </div>
                  <div>
                    <div className="font-display font-bold text-sm">{role.label}</div>
                    {role.description && (
                      <p className="text-xs text-muted-foreground mt-1 leading-snug">{role.description}</p>
                    )}
                  </div>
                  <span className="inline-flex items-center gap-1 text-xs font-bold text-accent opacity-0 group-hover:opacity-100 transition-opacity">
                    Select <ArrowRight className="w-3 h-3" />
                  </span>
                </button>
              ))}
            </div>
          </>
        ) : (
          <>
            <DialogHeader>
              <button
                type="button"
                onClick={() => setSelected(null)}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground mb-1 -ml-1"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Back to role selection
              </button>
              <DialogTitle className="font-display text-xl">
                {activeForm?.title || `Join as ${activeRole?.label}`}
              </DialogTitle>
              {activeForm?.description && (
                <DialogDescription>{activeForm.description}</DialogDescription>
              )}
            </DialogHeader>
            <RoleForm
              roleLabel={activeRole?.label}
              roleKey={selected}
              sections={activeForm?.sections || []}
              onDone={() => handleOpenChange(false)}
            />
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
