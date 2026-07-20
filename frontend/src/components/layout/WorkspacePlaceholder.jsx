import React from "react";
import PageContainer from "./PageContainer";
import PageHeader from "./PageHeader";
import { Card, CardContent } from "@/components/ui/card";

/* Shared "coming soon" shell for a workspace whose sidebar entry/route exists
   (the information architecture is real) but whose real page hasn't shipped
   yet — later phases replace the call site's WorkspacePlaceholder usage with
   the real page, no routing/nav change required. */
export default function WorkspacePlaceholder({ icon: Icon, eyebrow, title, description }) {
  return (
    <PageContainer className="max-w-3xl">
      <PageHeader eyebrow={eyebrow} eyebrowIcon={Icon} title={title} description={description} />
      <Card className="border-dashed border-2 mt-6">
        <CardContent className="p-10 text-center">
          {Icon && <Icon className="w-12 h-12 mx-auto text-muted-foreground mb-3" strokeWidth={1.5} />}
          <div className="font-display font-bold text-lg">Coming soon</div>
          <p className="text-sm text-muted-foreground mt-1 max-w-sm mx-auto">
            This workspace is being built next — it'll appear here as soon as it ships.
          </p>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
