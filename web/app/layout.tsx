import type { Metadata } from "next";
import { Archivo, Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";

import { SITE_DESCRIPTION, SITE_TITLE, TITLE_TEMPLATE } from "@/lib/page-meta";
import { SITE_URL } from "@/lib/site";

import "./globals.css";
import { pageMeta } from "./meta";
import { MotionRuntime } from "./motion";
import { SiteFooter } from "./site-footer";
import { SiteHeader } from "./site-header";
import { VersionGuard } from "./version-guard";

// The three families of the design. Archivo carries its width axis, so display lines can be set narrow.
const archivo = Archivo({ variable: "--font-archivo", subsets: ["latin"], axes: ["wdth"] });
const geist = Geist({ variable: "--font-geist", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  ...pageMeta({ title: SITE_TITLE, description: SITE_DESCRIPTION }),
  metadataBase: new URL(SITE_URL),
  // Pages name themselves ("Build journey"); the template adds " · First User". The home page keeps the default.
  title: { default: SITE_TITLE, template: TITLE_TEMPLATE },
};

// Applies a saved light or dark choice before the first paint, so the page never flashes the other theme.
const THEME_SCRIPT = `try{var t=localStorage.getItem("fu_theme");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-fu-theme",t)}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${archivo.variable} ${geist.variable} ${geistMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      {/* Browser extensions (e.g. ColorZilla's cz-shortcut-listen) add attributes to <body> before
          React hydrates. This ignores attribute mismatches on <body> only, not its children. */}
      <body suppressHydrationWarning>
        <VersionGuard />
        <div className="fu-root">
          <div aria-hidden className="fu-noise" />
          <a href="#main" className="sr-only-focusable fu-btn fu-btn-sm absolute left-4 top-4 z-[80]">
            Skip to content
          </a>
          <Suspense fallback={<header className="fu-header" style={{ height: 72 }} />}>
            <SiteHeader />
          </Suspense>
          <div id="main">{children}</div>
          <Suspense fallback={null}>
            <SiteFooter />
            <MotionRuntime />
          </Suspense>
        </div>
      </body>
    </html>
  );
}
