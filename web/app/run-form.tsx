"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import type { ApiError } from "@/lib/types";

type FormError = { field: "url" | "permission" | "form"; title?: string; message: string };

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

    if (!url) return setError({ field: "url", message: "Enter your app's address." });
    if (!permission) {
      return setError({ field: "permission", message: "Please confirm you're allowed to test this app." });
    }

    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, goal, permission }),
      });
      const body = (await response.json().catch(() => null)) as { id?: string } | ApiError | null;
      if (response.ok && body && "id" in body && body.id) {
        router.push(`/run/${body.id}`);
        return;
      }
      const apiError = body && "error" in body ? body : null;
      const code = apiError?.error ?? "server_error";
      setError({
        field: code === "invalid_url" ? "url" : code === "permission_required" ? "permission" : "form",
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
