import "server-only";

import { createHmac } from "node:crypto";

// The first address in X-Forwarded-For is the client when a trusted proxy
// (such as Vercel) sets the header. Without such a proxy it can be forged, so
// the rate limit is a speed bump, not a guarantee.
export function clientIp(headers: Headers): string {
  const forwarded = headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  return forwarded || headers.get("x-real-ip")?.trim() || "unknown";
}

// A keyed hash, so the stored value cannot be reversed by hashing every IPv4
// address. IP_HASH_SECRET is optional; the service role key is already a
// server-only secret, so it is the fallback key.
export function hashIp(ip: string): string {
  const secret = process.env.IP_HASH_SECRET || process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!secret) throw new Error("No secret available to hash visitor IPs");
  return createHmac("sha256", secret).update(ip).digest("hex");
}
