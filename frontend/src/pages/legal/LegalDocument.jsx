import React from "react";
import { useParams, Navigate } from "react-router-dom";
import { getLegalDoc } from "@/content/legal";
import LegalPageLayout from "@/components/legal/LegalPageLayout";

export default function LegalDocument() {
  const { slug } = useParams();
  const doc = getLegalDoc(slug);

  if (!doc) return <Navigate to="/legal" replace />;

  return <LegalPageLayout doc={doc} />;
}
