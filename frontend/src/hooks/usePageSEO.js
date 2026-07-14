import { useEffect } from "react";

const SITE_NAME = "CourtBazaar";
const DEFAULT_OG_IMAGE = "/images/cbLogo-navbar.png";

function upsertMeta(attr, key, content) {
  if (!content) return;
  let el = document.head.querySelector(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function upsertLink(rel, href) {
  if (!href) return;
  let el = document.head.querySelector(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

/* Client-side page metadata: title, description, canonical, robots, Open
   Graph, Twitter Card. This is a CRA SPA with no SSR, so crawlers that don't
   execute JS (WhatsApp/Facebook link previews) won't see these — but
   search engines that do run JS (Googlebot) will, and the browser tab title/
   history/bookmarks are always correct. No new dependency; plain DOM. */
export default function usePageSEO({
  title,
  description,
  path,
  robots = "index, follow",
  image = DEFAULT_OG_IMAGE,
  type = "website",
}) {
  useEffect(() => {
    const fullTitle = title ? `${title} | ${SITE_NAME}` : SITE_NAME;
    document.title = fullTitle;

    const canonicalUrl = path ? `${window.location.origin}${path}` : window.location.href;
    const absoluteImage = image?.startsWith("http") ? image : `${window.location.origin}${image}`;

    upsertMeta("name", "description", description);
    upsertMeta("name", "robots", robots);
    upsertLink("canonical", canonicalUrl);

    upsertMeta("property", "og:title", fullTitle);
    upsertMeta("property", "og:description", description);
    upsertMeta("property", "og:type", type);
    upsertMeta("property", "og:url", canonicalUrl);
    upsertMeta("property", "og:site_name", SITE_NAME);
    upsertMeta("property", "og:image", absoluteImage);

    upsertMeta("name", "twitter:card", "summary_large_image");
    upsertMeta("name", "twitter:title", fullTitle);
    upsertMeta("name", "twitter:description", description);
    upsertMeta("name", "twitter:image", absoluteImage);
  }, [title, description, path, robots, image, type]);
}
