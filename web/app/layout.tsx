import type { Metadata } from "next";
import { Archivo, Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";

import "./globals.css";
import { MotionRuntime } from "./motion";
import { SiteFooter } from "./site-footer";
import { SiteHeader } from "./site-header";

// The three families of the design. Archivo carries its width axis, so display lines can be set narrow.
const archivo = Archivo({ variable: "--font-archivo", subsets: ["latin"], axes: ["wdth"] });
const geist = Geist({ variable: "--font-geist", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "First User",
  description:
    "Find out whether a stranger can actually use your product, before you spend money acquiring users. A first-time visitor tries one goal in a real browser and reports honestly what happened.",
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
