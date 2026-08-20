import React from "react";
import PageContainer from "./PageContainer";
import PageHeader from "./PageHeader";
import EmptyState from "@/components/shared/EmptyState";

/* Shared "coming soon" shell for a workspace whose sidebar entry/route exists
   (the information architecture is real) but whose real page hasn't shipped
   yet — later phases replace the call site's WorkspacePlaceholder usage with
   the real page, no routing/nav change required. */
export default function WorkspacePlaceholder({ icon: Icon, eyebrow, title, description }) {
  return (
    <PageContainer className="max-w-3xl">
      <PageHeader eyebrow={eyebrow} eyebrowIcon={Icon} title={title} description={description} />
      <EmptyState
        className="mt-6"
        size="lg"
        icon={Icon}
        title="Coming soon"
        description="This workspace is being built next — it'll appear here as soon as it ships."
      />
    </PageContainer>
  );
}
