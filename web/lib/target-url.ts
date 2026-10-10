import "server-only";

import { lookup } from "node:dns/promises";
import { isIP } from "node:net";

export type UrlCheck = { ok: true; url: string } | { ok: false; message: string };

const MAX_URL_LENGTH = 2048;
const BLOCKED_SUFFIXES = [".localhost", ".local", ".internal", ".intranet", ".lan", ".home.arpa", ".corp"];
const DNS_TIMEOUT_MS = 3000;

const PRIVATE_MESSAGE =
  "That address points to a private or local network. Use your app's public address, the one a visitor would type.";

/**
 * Accept only a public http(s) address on the default port. The worker's
 * browser resolves the name again later and the site can redirect, so this
 * stops honest mistakes and casual abuse, not a determined DNS-rebinding attack.
 */
export async function checkTargetUrl(input: string): Promise<UrlCheck> {
  const text = input.trim();
  if (!text) return { ok: false, message: "Enter your app's address." };
  if (text.length > MAX_URL_LENGTH) return { ok: false, message: "That address is too long." };

  let url: URL;
  try {
    url = new URL(/^[a-z][a-z0-9+.-]*:/i.test(text) ? text : `https://${text}`);
  } catch {
    return { ok: false, message: "That doesn't look like a web address. Try something like https://example.com." };
  }

  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return { ok: false, message: "Only http:// and https:// addresses can be tested." };
  }
  if (url.username || url.password) {
    return { ok: false, message: "Remove the username and password from the address." };
  }
  // The URL parser drops default ports (80 for http, 443 for https), so any port left is unusual.
  if (url.port) {
    return { ok: false, message: "Use your app's public address without a port number (like :3000)." };
  }

  const host = url.hostname.toLowerCase().replace(/^\[|\]$/g, "").replace(/\.$/, "");
  if (isIP(host)) {
    if (isPrivateAddress(host)) return { ok: false, message: PRIVATE_MESSAGE };
  } else {
    if (host === "localhost" || BLOCKED_SUFFIXES.some((suffix) => host.endsWith(suffix))) {
      return { ok: false, message: PRIVATE_MESSAGE };
    }
    if (!host.includes(".")) {
      return { ok: false, message: "Use the full public address of your app, like https://example.com." };
    }
    let addresses: { address: string }[];
    try {
      addresses = await withTimeout(lookup(host, { all: true, verbatim: true }), DNS_TIMEOUT_MS);
    } catch {
      return { ok: false, message: `We couldn't find a site at ${host}. Check the address and try again.` };
    }
    if (addresses.length === 0 || addresses.some(({ address }) => isPrivateAddress(address))) {
      return { ok: false, message: PRIVATE_MESSAGE };
    }
  }

  url.hash = "";
  return { ok: true, url: url.href };
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("timeout")), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

export function isPrivateAddress(address: string): boolean {
  const version = isIP(address);
  if (version === 4) return isPrivateIPv4(address);
  if (version === 6) return isPrivateIPv6(address);
  return true;
}

function isPrivateIPv4(address: string): boolean {
  const [a, b, c] = address.split(".").map(Number);
  return (
    a === 0 || // "this" network
    a === 10 || // private
    a === 127 || // loopback
    (a === 100 && b >= 64 && b <= 127) || // carrier-grade NAT
    (a === 169 && b === 254) || // link-local, including cloud metadata
    (a === 172 && b >= 16 && b <= 31) || // private
    (a === 192 && b === 0 && (c === 0 || c === 2)) || // protocol assignments, documentation
    (a === 192 && b === 168) || // private
    (a === 198 && (b === 18 || b === 19)) || // benchmarking
    (a === 198 && b === 51 && c === 100) || // documentation
    (a === 203 && b === 0 && c === 113) || // documentation
    a >= 224 // multicast, reserved, broadcast
  );
}

function isPrivateIPv6(address: string): boolean {
  const groups = expandIPv6(address);
  if (!groups) return true;
  const zeros = (from: number, to: number) => groups.slice(from, to).every((g) => g === 0);

  if (zeros(0, 8)) return true; // ::
  if (zeros(0, 7) && groups[7] === 1) return true; // ::1
  if (zeros(0, 5) && groups[5] === 0xffff) return isPrivateIPv4(embeddedIPv4(groups)); // ::ffff:a.b.c.d
  if (zeros(0, 6)) return isPrivateIPv4(embeddedIPv4(groups)); // deprecated ::a.b.c.d
  if (groups[0] === 0x64 && groups[1] === 0xff9b && zeros(2, 6)) return isPrivateIPv4(embeddedIPv4(groups)); // NAT64

  const first = groups[0];
  return (
    (first & 0xfe00) === 0xfc00 || // unique local fc00::/7
    (first & 0xffc0) === 0xfe80 || // link-local fe80::/10
    (first & 0xff00) === 0xff00 || // multicast
    (first === 0x2001 && groups[1] === 0x0db8) // documentation
  );
}

function embeddedIPv4(groups: number[]): string {
  return [groups[6] >> 8, groups[6] & 0xff, groups[7] >> 8, groups[7] & 0xff].join(".");
}

function expandIPv6(address: string): number[] | null {
  let text = address.split("%")[0];
  const dotted = text.match(/(\d+)\.(\d+)\.(\d+)\.(\d+)$/);
  if (dotted) {
    const [a, b, c, d] = dotted.slice(1).map(Number);
    text = text.slice(0, -dotted[0].length) + `${((a << 8) | b).toString(16)}:${((c << 8) | d).toString(16)}`;
  }
  const halves = text.split("::");
  if (halves.length > 2) return null;
  const parse = (part: string) => (part ? part.split(":").map((g) => parseInt(g, 16)) : []);
  const head = parse(halves[0]);
  const tail = halves.length === 2 ? parse(halves[1]) : [];
  const missing = 8 - head.length - tail.length;
  if (missing < 0 || (halves.length === 1 && missing !== 0)) return null;
  const groups = [...head, ...Array<number>(missing).fill(0), ...tail];
  return groups.some((g) => Number.isNaN(g) || g < 0 || g > 0xffff) ? null : groups;
}
