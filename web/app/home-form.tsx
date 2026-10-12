"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import type { ApiError } from "@/lib/types";

import { RunForm, type RunFormInitial } from "./run-form";

type Mode = "test" | "understand";

const MODES: { value: Mode; label: string; help: string }[] = [
  { value: "test", label: "Test my website", help: "A first-time visitor tries a goal on it and reports where they got stuck." },
  {
    value: "understand",
    label: "Understand this website",
    help: "Read a few of its public pages and get a short brief: what it does, who it's for, and goals worth testing.",
  },
];

export function HomeForm({ mode: initialMode, initial }: { mode: Mode; initial: RunFormInitial }) {
  const [mode, setMode] = useState<Mode>(initialMode);
  return (
    <div className="space-y-6">
      <fieldset className="space-y-2">
        <legend className="sr-only">What do you want to do?</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {MODES.map((option) => (
            <label
              key={option.value}
              className={
                "flex cursor-pointer items-start gap-3 rounded-xl border p-4 " +
                (mode === option.value ? "border-accent bg-surface" : "border-line bg-surface hover:border-accent/60")
              }
            >
              <input
                type="radio"
                name="mode"
                value={option.value}
                checked={mode === option.value}
                onChange={() => setMode(option.value)}
                className="mt-1 size-5 shrink-0 accent-accent"
              />
              <span>
                <span className="block font-medium">{option.label}</span>
                <span className="mt-0.5 block text-sm text-muted">{option.help}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      {initial.brief && mode === "test" && (
        <p className="rounded-xl border border-line bg-surface p-4 text-sm text-muted">
          Filled in from the product brief of this site. Change anything you like before you start.
        </p>
      )}

      {mode === "test" ? <RunForm initial={initial} /> : <UnderstandForm initialUrl={initial.url} />}
    </div>
  );
}

function UnderstandForm({ initialUrl }: { initialUrl: string }) {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ title?: string; message: string } | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const url = String(new FormData(event.currentTarget).get("url") ?? "").trim();
    if (!url) return setError({ message: "Enter the website's address." });
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/briefs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const body = (await response.json().catch(() => null)) as { id?: string } | ApiError | null;
      if (response.ok && body && "id" in body && body.id) {
        router.push(`/brief/${body.id}`);
        return;
      }
      const apiError = body && "error" in body ? body : null;
      setError({
        title: apiError?.error === "rate_limited" ? "You've reached the hourly limit" : undefined,
        message: apiError?.message ?? "Something went wrong on our side. Please try again in a minute.",
      });
    } catch {
      setError({ title: "Couldn't reach the server", message: "Check your connection and try again." });
    }
    setSubmitting(false);
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-6">
      <div>
        <label htmlFor="understand-url" className="font-medium">
          The website&apos;s address
        </label>
        <input
          id="understand-url"
          name="url"
          type="url"
          inputMode="url"
          autoComplete="url"
          placeholder="https://example.com"
          defaultValue={initialUrl}
          required
          aria-invalid={!!error}
          className="mt-2 block w-full rounded-lg border border-line bg-surface px-3.5 py-3 text-base text-foreground placeholder:text-subtle focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
        />
        <p className="mt-2 text-sm text-subtle">
          We read the homepage and up to eight more public pages (about, product, pricing, docs and so on), follow the
          site&apos;s robots.txt, and never sign in.
        </p>
      </div>

      {error && (
        <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-4 text-sm">
          {error.title && <p className="font-medium text-danger">{error.title}</p>}
          <p className="mt-1 text-foreground">{error.message}</p>
        </div>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-lg bg-accent px-5 py-3 font-medium text-white hover:bg-accent-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-2 disabled:opacity-60 sm:w-auto dark:text-background"
      >
        {submitting ? "Starting…" : "Understand this website"}
      </button>
    </form>
  );
}
