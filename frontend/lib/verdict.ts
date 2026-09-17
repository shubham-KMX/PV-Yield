/**
 * Turns a measured AnalyzeResult into a plain-language verdict.
 *
 * Unlike the old project's fake 0-100 "solar potential score", this reads
 * REAL signals from our pipeline — payback period, system size, usable
 * area — and states an honest recommendation.
 */
import type { AnalyzeResult } from "./api";

export type VerdictTier = "excellent" | "good" | "moderate" | "limited" | "none";

export interface Verdict {
  tier: VerdictTier;
  headline: string;
  detail: string;
}

export function computeVerdict(r: AnalyzeResult): Verdict {
  // No panels fit at all.
  if (r.panel_count === 0) {
    return {
      tier: "none",
      headline: "Not viable as-is",
      detail:
        r.message ??
        "We couldn't fit panels on the usable roof area. Try marking a larger, unobstructed section.",
    };
  }

  const payback = r.financials?.payback_years ?? null;
  const kw = r.system_size_kw ?? 0;

  // System vastly over-produces for the entered usage (never pays back).
  if (payback === null) {
    return {
      tier: "moderate",
      headline: "Bigger than your usage needs",
      detail:
        `This roof fits a ${kw} kW system, which generates more than your ` +
        `current consumption can offset. Increase your monthly usage, or a ` +
        `smaller array, to see a realistic payback.`,
    };
  }

  // Payback drives the tier — the clearest real-money signal.
  if (payback <= 4) {
    return {
      tier: "excellent",
      headline: "Excellent fit",
      detail: `A ${kw} kW system pays for itself in about ${payback} years. Strongly worth pursuing.`,
    };
  }
  if (payback <= 7) {
    return {
      tier: "good",
      headline: "Good investment",
      detail: `A ${kw} kW system pays back in roughly ${payback} years — a solid return.`,
    };
  }
  if (payback <= 12) {
    return {
      tier: "moderate",
      headline: "Worth considering",
      detail: `Payback is around ${payback} years. Reasonable, especially with rising tariffs.`,
    };
  }
  return {
    tier: "limited",
    headline: "Longer payback",
    detail: `Payback is about ${payback} years at this usage. Solar still helps, but the returns are slower.`,
  };
}
