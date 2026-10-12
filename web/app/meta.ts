// The Metadata of a page: its title and description, repeated in the share cards for X and LinkedIn, with the
// share image public/og.png. The image is named on every page because a page's openGraph replaces the layout's
// whole object, so a file-convention image (app/opengraph-image.png) would vanish from any page that sets one.

import type { Metadata } from "next";

import { SITE_TITLE, TITLE_TEMPLATE, type PageText } from "@/lib/page-meta";
import { SOCIAL } from "@/lib/site";

const IMAGE = { url: "/og.png", width: 1200, height: 630, alt: SITE_TITLE };

export function pageMeta({ title, description }: PageText, extra: Metadata = {}): Metadata {
  // The cards do not get the layout's title template, so their title is written out in full.
  const full = title === SITE_TITLE ? title : TITLE_TEMPLATE.replace("%s", title);
  return {
    title: title === SITE_TITLE ? { absolute: title } : title,
    description,
    openGraph: { type: "website", siteName: "First User", title: full, description, images: [IMAGE] },
    twitter: { card: "summary_large_image", title: full, description, creator: SOCIAL.x.handle, images: [IMAGE] },
    ...extra,
  };
}
