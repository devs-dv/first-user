import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "First User",
  description: "Paste your app's link. A first-time user tries it and tells you where they got stuck.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      {/* Browser extensions (e.g. ColorZilla's cz-shortcut-listen) add attributes to <body> before
          React hydrates. This ignores attribute mismatches on <body> only, not its children. */}
      <body suppressHydrationWarning className="flex min-h-full flex-col font-sans text-base leading-relaxed">
        <header className="border-b border-line">
          <div className="mx-auto flex max-w-3xl items-center px-4 py-4 sm:px-6">
            <Link href="/" className="font-semibold tracking-tight">
              First User
            </Link>
          </div>
        </header>
        <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-10 sm:px-6 sm:py-14">{children}</main>
        <footer className="border-t border-line">
          <p className="mx-auto max-w-3xl px-4 py-6 text-sm text-subtle sm:px-6">
            First User is a simulated visitor. Findings are leads to check, not verdicts.
          </p>
        </footer>
      </body>
    </html>
  );
}
