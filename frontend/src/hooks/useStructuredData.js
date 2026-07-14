import { useEffect } from "react";

/* Injects a JSON-LD <script type="application/ld+json"> tag scoped to a
   unique id, replacing any previous tag with the same id on re-render and
   removing it on unmount. No new dependency — plain DOM. */
export default function useStructuredData(id, schema) {
  useEffect(() => {
    if (!schema) return undefined;
    let el = document.getElementById(id);
    if (!el) {
      el = document.createElement("script");
      el.type = "application/ld+json";
      el.id = id;
      document.head.appendChild(el);
    }
    el.textContent = JSON.stringify(schema);
    return () => {
      el?.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, JSON.stringify(schema)]);
}

export function organizationSchema({ companyInfo }) {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: companyInfo.brandName,
    legalName: companyInfo.legalName,
    url: window.location.origin,
    logo: `${window.location.origin}/images/cbLogo-navbar.png`,
    sameAs: companyInfo.socialLinks.map((s) => s.href),
    ...(companyInfo.supportEmail?.value && { email: companyInfo.supportEmail.value }),
  };
}

export function breadcrumbSchema(items) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: item.label,
      item: item.href ? `${window.location.origin}${item.href}` : undefined,
    })),
  };
}
