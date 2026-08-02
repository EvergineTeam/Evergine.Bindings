/** Formatting shared by the pages. Everything runs at build time. */

export function num(n: number | undefined): string {
  if (!n) return "—";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return String(n);
}

export function money(n: number | undefined): string {
  return "$" + (n ?? 0).toFixed(2);
}

export function duration(s: number | undefined): string {
  if (!s) return "—";
  if (s < 60) return Math.round(s) + "s";
  return Math.floor(s / 60) + "m " + Math.round(s % 60) + "s";
}

export function when(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
    timeZone: "UTC",
  }) + " UTC";
}

/** Days elapsed, or null when there is no date to measure from. */
export function daysSince(iso: string | null | undefined): number | null {
  if (!iso) return null;
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
}

/** Repository name to URL segment: "Vulkan.NET" -> "vulkan-net". */
export function slug(repo: string): string {
  return repo.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

/** A published package older than this is worth looking at. Two months allows
 *  a skipped cycle without crying wolf; three would hide a broken one. */
export const STALE_DAYS = 60;

export function freshnessClass(days: number | null): string {
  if (days === null) return "idle";
  if (days <= 35) return "ok";
  if (days <= STALE_DAYS) return "warn";
  return "bad";
}
