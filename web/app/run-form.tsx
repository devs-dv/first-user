"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import type { ApiError } from "@/lib/types";

type Access = "public" | "link" | "account" | "signup";

const ACCESS_OPTIONS: { value: Access; label: string; help: string }[] = [
  { value: "public", label: "No login", help: "Look at what is public. This is the default." },
  { value: "link", label: "I have a demo or guest link", help: "The visit begins at a page that is already past the login." },
  { value: "account", label: "Use a test account", help: "Sign in with a throwaway email and password you give." },
  { value: "signup", label: "Let it sign up by itself", help: "The visitor makes up a test account on your signup form." },
];

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

// What the form starts with: empty, or filled from a suggested journey on a product brief.
export type RunFormInitial = { url: string; goal: string; success: string; brief: string };

export function RunForm({ initial }: { initial?: RunFormInitial }) {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<FormError | null>(null);
  const [access, setAccess] = useState<Access>("public");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const url = String(form.get("url") ?? "").trim();
    const goal = String(form.get("goal") ?? "").trim();
    const success = String(form.get("success") ?? "").trim();
    const permission = form.get("permission") === "on";
    // Only the fields of the chosen option exist in the form, so nothing else is read or sent.
    const startUrl = access === "link" ? String(form.get("startUrl") ?? "").trim() : "";
    const testEmail = access === "account" ? String(form.get("testEmail") ?? "").trim() : "";
    const testPassword = access === "account" ? String(form.get("testPassword") ?? "") : "";

    if (!url) return setError({ field: "url", message: "Enter your app's address." });
    if (!permission) {
      return setError({ field: "permission", message: "Please confirm you're allowed to test this app." });
    }

    if (access === "link" && !startUrl) {
      return setError({ field: "startUrl", message: "Enter the demo or guest link, or choose another option." });
    }
    if (access === "account" && (!testEmail || !testPassword)) {
      return setError({
        field: "credentials",
        message: "Enter both a test email and a test password, or choose another option.",
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
          success: success || undefined,
          briefId: initial?.brief || undefined,
          permission,
          access,
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
          defaultValue={initial?.url}
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
          defaultValue={initial?.goal}
          aria-describedby="goal-hint"
          className={inputClass}
        />
        <p id="goal-hint" className="mt-2 text-sm text-subtle">
          Leave this empty and they&apos;ll work out what the product does and try its main feature.
        </p>
      </div>

      <div>
        <label htmlFor="success" className="font-medium">
          What would success look like? <span className="font-normal text-subtle">(optional)</span>
        </label>
        <textarea
          id="success"
          name="success"
          rows={2}
          maxLength={300}
          placeholder="For example: a confirmation page that names the new project"
          defaultValue={initial?.success}
          className={inputClass}
        />
      </div>

      <fieldset className="space-y-3" aria-describedby="access-hint">
        <legend className="font-medium">How should the visitor get in?</legend>
        <p id="access-hint" className="text-sm text-subtle">
          Apps that only offer Google or GitHub login: use a demo or guest link.
        </p>
        <div className="space-y-2">
          {ACCESS_OPTIONS.map((option) => (
            <label
              key={option.value}
              className={
                "flex cursor-pointer items-start gap-3 rounded-xl border p-4 " +
                (access === option.value ? "border-accent bg-surface" : "border-line bg-surface hover:border-accent/60")
              }
            >
              <input
                type="radio"
                name="access"
                value={option.value}
                checked={access === option.value}
                onChange={() => setAccess(option.value)}
                className="mt-1 size-5 shrink-0 accent-accent"
              />
              <span>
                <span className="block font-medium">{option.label}</span>
                <span className="mt-0.5 block text-sm text-muted">{option.help}</span>
              </span>
            </label>
          ))}
        </div>

        {access === "link" && (
          <div className="rounded-xl border border-line bg-surface p-4">
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
        )}

        {access === "account" && (
          <div className="space-y-4 rounded-xl border border-line bg-surface p-4">
            <p className="rounded-lg border border-warning/30 bg-warning-soft p-3 text-sm">
              Use a throwaway account. Kept only for this run, never shown to the AI, deleted when the run ends.
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
          </div>
        )}

        {access === "signup" && (
          <p className="rounded-xl border border-line bg-surface p-4 text-sm text-muted">
            Works for email-and-password signup without email verification.
          </p>
        )}
      </fieldset>

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
