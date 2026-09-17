"use client";

/**
 * Verdict — a plain-language recommendation banner at the top of the
 * results, computed from the real measured numbers (payback, system size).
 */
import { motion } from "framer-motion";
import { CheckCircle2, ThumbsUp, Info, Clock, XCircle } from "lucide-react";
import type { AnalyzeResult } from "@/lib/api";
import { computeVerdict, type VerdictTier } from "@/lib/verdict";

const STYLES: Record<
  VerdictTier,
  { border: string; bg: string; text: string; Icon: React.ElementType }
> = {
  excellent: {
    border: "border-[rgba(34,197,94,0.4)]",
    bg: "bg-[rgba(240,253,244,0.9)]",
    text: "text-sunset-green",
    Icon: CheckCircle2,
  },
  good: {
    border: "border-[rgba(34,197,94,0.35)]",
    bg: "bg-[rgba(240,253,244,0.7)]",
    text: "text-sunset-green",
    Icon: ThumbsUp,
  },
  moderate: {
    border: "border-[rgba(249,115,22,0.35)]",
    bg: "bg-[rgba(255,247,237,0.9)]",
    text: "text-sunset-orange",
    Icon: Info,
  },
  limited: {
    border: "border-sunset-line",
    bg: "bg-white",
    text: "text-sunset-muted",
    Icon: Clock,
  },
  none: {
    border: "border-[rgba(224,71,91,0.35)]",
    bg: "bg-[rgba(254,242,242,0.9)]",
    text: "text-sunset-coral",
    Icon: XCircle,
  },
};

export default function Verdict({ result }: { result: AnalyzeResult }) {
  const v = computeVerdict(result);
  const s = STYLES[v.tier];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className={`mx-auto mb-8 flex max-w-[1120px] items-start gap-4 rounded-2xl border ${s.border} ${s.bg} p-5 shadow-[0_6px_20px_rgba(180,120,80,0.08)]`}
    >
      <s.Icon className={`mt-0.5 h-7 w-7 flex-shrink-0 ${s.text}`} />
      <div>
        <div className={`text-lg font-extrabold ${s.text}`}>{v.headline}</div>
        <p className="mt-1 text-sm leading-relaxed text-foreground/80">
          {v.detail}
        </p>
      </div>
    </motion.div>
  );
}
