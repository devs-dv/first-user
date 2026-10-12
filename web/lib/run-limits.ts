// The two limits every run shares (test, retest, understand and founder brief runs alike): how many runs
// may wait in the queue, and how many one visitor may start per hour. The hourly limit is set on the
// server with RUNS_PER_HOUR (a whole number, default 5); it is not a NEXT_PUBLIC_ value, so it is read
// when a request comes in, not when the app is built.

export const MAX_QUEUED = 20;
export const DEFAULT_RUNS_PER_HOUR = 5;

export function runsPerHourFrom(value: string | undefined): number {
  const text = (value ?? "").trim();
  if (!/^\d+$/.test(text)) return DEFAULT_RUNS_PER_HOUR;
  const n = Number(text);
  return n >= 1 && n <= 1000 ? n : DEFAULT_RUNS_PER_HOUR;
}

export function runsPerHour(): number {
  return runsPerHourFrom(process.env.RUNS_PER_HOUR);
}

// The visitor has hit the limit, so no runs are left; the message says so, and when the next one frees up.
export function rateLimitMessage(limit: number, retryAfterSeconds: number): string {
  const minutes = Math.max(1, Math.ceil(retryAfterSeconds / 60));
  return (
    `You've used ${limit} of ${limit} run${limit === 1 ? "" : "s"} this hour, so you have 0 left. ` +
    `You can start another in about ${minutes} minute${minutes === 1 ? "" : "s"}.`
  );
}

// The 429 answer every run route gives when the database says the visitor is over the limit.
export function rateLimited(limit: number, retryAfterSeconds: number | undefined, headers?: HeadersInit): Response {
  const seconds = Math.max(60, retryAfterSeconds ?? 3600);
  const merged = new Headers(headers);
  merged.set("Retry-After", String(seconds));
  return Response.json(
    {
      error: "rate_limited",
      message: rateLimitMessage(limit, seconds),
      limit,
      remaining: 0,
      retryAfterSeconds: seconds,
    },
    { status: 429, headers: merged },
  );
}
