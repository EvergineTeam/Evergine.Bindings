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

/** How far a repository's agents have fallen behind the toolbox.
 *
 *  Current is green, one release back is amber, two or more is red. The point
 *  is not that an old pin is broken — it usually is not — but that the gap is
 *  invisible otherwise: moving the `v1` tag does nothing to a repository until
 *  somebody recompiles it, so a binding can sit on an old release indefinitely
 *  without a single red run to give it away.
 */
export function toolboxClass(tb: any): string {
  // Accepts the toolbox object, not just `behind`: a repository that only calls
  // the reusable workflows has nothing pinned and so cannot be behind, but
  // colouring it green would make it look like an agent repo that is up to date.
  // Those are different facts and the chip should not blur them.
  const behind = typeof tb === "number" ? tb : tb?.behind;
  if (tb && typeof tb !== "number" && tb.consumer_only) return "idle";
  if (behind === null || behind === undefined) return "idle";
  if (behind === 0) return "ok";
  if (behind === 1) return "warn";
  return "bad";
}

export function toolboxLabel(tb: any): string {
  if (!tb) return "does not use the toolbox";
  // No agents compiled here, but the toolbox's reusable workflows are called.
  // There is no pin to drift: `uses: ...@v1` resolves the tag when the workflow
  // runs, so this repository is on the current release by construction.
  if (tb.consumer_only) {
    const refs = (tb.workflow_refs ?? []).join(", ");
    return `reusable workflows @${refs} · no agents, nothing to pin`;
  }
  if (!tb.version) return "unknown pin";
  if (tb.behind === 0) return `${tb.version} · current`;
  const releases = tb.behind === 1 ? "1 release" : `${tb.behind} releases`;
  // A release that only touched a reusable workflow leaves the agents
  // byte-identical. Saying "behind" without saying that would be true and
  // misleading at the same time.
  return `${tb.version} · ${releases} behind${tb.agents_differ === false ? ", agents unchanged" : ""}`;
}
