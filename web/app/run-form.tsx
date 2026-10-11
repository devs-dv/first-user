"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import type { ApiError } from "@/lib/types";

type FormError = {
  field: "url" | "startUrl" | "credentials" | "permission" | "form";
  title?: string;
  message: string;
};

const TITLES: Record<string, string> = {
  queue_full: "The queue is full",
  rate_limited: "You've reached the hourly limit",
  server_error: "Something went wrong",
};

export function RunForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<FormError | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const url = String(form.get("url") ?? "").trim();
    const goal = String(form.get("goal") ?? "").trim();
    const permission = form.get("permission") === "on";
    const startUrl = String(form.get("startUrl") ?? "").trim();
    const testEmail = String(form.get("testEmail") ?? "").trim();
    const testPassword = String(form.get("testPassword") ?? "");

    if (!url) return setError({ field: "url", message: "Enter your app's address." });
    if (!permission) {
      return setError({ field: "permission", message: "Please confirm you're allowed to test this app." });
    }

    if (Boolean(testEmail) !== Boolean(testPassword)) {
      return setError({
        field: "credentials",
        message: "Enter both a test email and a test password, or leave both empty.",
      });
    }

    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          goal,
          permission,
          startUrl: startUrl || undefined,
          testEmail: testEmail || undefined,
          testPassword: testPassword || undefined,
        }),
      });
      const body = (await response.json().catch(() => null)) as { id?: string } | ApiError | null;
      if (response.ok && body && "id" in body && body.id) {
        router.push(`/run/${body.id}`);
        return;
      }
      const apiError = body && "error" in body ? body : null;
      const code = apiError?.error ?? "server_error";
      setError({
        field:
          code === "invalid_url"
            ? "url"
            : code === "invalid_start_url"
              ? "startUrl"
              : code === "invalid_credentials"
                ? "credentials"
                : code === "permission_required"
                  ? "permission"
                  : "form",
        title: TITLES[code],
        message: apiError?.message ?? "Something went wrong on our side. Please try again in a minute.",
      });
    } catch {
      setError({ field: "form", title: "Couldn't reach the server", message: "Check your connection and try again." });
    }
    setSubmitting(false);
  }

  const inputClass =
    "mt-2 block w-full rounded-lg border border-line bg-surface px-3.5 py-3 text-base text-foreground " +
    "placeholder:text-subtle focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30";

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-6">
      <div>
        <label htmlFor="url" className="font-medium">
          Your app&apos;s address
        </label>
        <input
          id="url"
          name="url"
          type="url"
          inputMode="url"
          autoComplete="url"
          placeholder="https://yourapp.com"
          required
          aria-invalid={error?.field === "url"}
          aria-describedby={error?.field === "url" ? "url-error" : undefined}
          className={inputClass}
        />
        {error?.field === "url" && (
          <p id="url-error" className="mt-2 text-sm text-danger">
            {error.message}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="goal" className="font-medium">
          What should they try to do? <span className="font-normal text-subtle">(optional)</span>
        </label>
        <textarea
          id="goal"
          name="goal"
          rows={2}
          maxLength={500}
          placeholder="For example: sign up and create your first project"
          aria-describedby="goal-hint"
          className={inputClass}
        />
        <p id="goal-hint" className="mt-2 text-sm text-subtle">
          Leave this empty and they&apos;ll work out what the product does and try its main feature.
        </p>
      </div>

      <details className="rounded-xl border border-line bg-surface p-4" open={error?.field === "startUrl" || error?.field === "credentials"}>
        <summary className="cursor-pointer font-medium">
          Is your app behind a login? <span className="font-normal text-subtle">(optional)</span>
        </summary>
        <div className="mt-4 space-y-6">
          <p className="text-sm text-muted">
            Without anything here, the visitor sees what any newcomer sees and may try to sign up with a made-up test
            account. For a deeper visit, give it a way in:
          </p>

          <div>
            <label htmlFor="startUrl" className="font-medium">
              Start link
            </label>
            <input
              id="startUrl"
              name="startUrl"
              type="url"
              inputMode="url"
              placeholder="https://yourapp.com/demo"
              aria-invalid={error?.field === "startUrl"}
              aria-describedby="startUrl-hint"
              className={inputClass}
            />
            <p id="startUrl-hint" className="mt-2 text-sm text-subtle">
              A demo page, guest mode or preview build that is already past the login. The visit begins here.
            </p>
            {error?.field === "startUrl" && <p className="mt-2 text-sm text-danger">{error.message}</p>}
          </div>

          <fieldset className="space-y-4">
            <legend className="font-medium">Test login</legend>
            <p className="rounded-lg border border-warning/30 bg-warning-soft p-3 text-sm">
              Use a <strong>throwaway test account</strong> with no real data, never a real person&apos;s login. We keep
              it only until a browser picks up your run, then delete it. The AI visitor never sees it, and it is never
              written to the report.
            </p>
            <div>
              <label htmlFor="testEmail" className="text-sm font-medium">
                Test email
              </label>
              <input
                id="testEmail"
                name="testEmail"
                type="email"
                autoComplete="off"
                placeholder="test@yourapp.com"
                aria-invalid={error?.field === "credentials"}
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="testPassword" className="text-sm font-medium">
                Test password
              </label>
              <input
                id="testPassword"
                name="testPassword"
                type="password"
                autoComplete="new-password"
                aria-invalid={error?.field === "credentials"}
                className={inputClass}
              />
            </div>
            {error?.field === "credentials" && <p className="text-sm text-danger">{error.message}</p>}
          </fieldset>
        </div>
      </details>

      <div>
        <label className="flex items-start gap-3">
          <input
            name="permission"
            type="checkbox"
            required
            aria-invalid={error?.field === "permission"}
            className="mt-1 size-5 shrink-0 accent-accent"
          />
          <span>This is my app or I have permission to test it</span>
        </label>
        {error?.field === "permission" && <p className="mt-2 text-sm text-danger">{error.message}</p>}
      </div>

      {error?.field === "form" && (
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
        {submitting ? "Starting…" : "Start the visit"}
      </button>
    </form>
  );
}
