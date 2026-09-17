"use client";

/**
 * Results section: renders the analysis as sunset-styled metric cards.
 * Shows a friendly empty state before any analysis, and handles the
 * "no panels fit" partial result.
 */
import { motion } from "framer-motion";
import { satelliteImageUrl, type AnalyzeResult } from "@/lib/api";
import MonthlyChart from "./MonthlyChart";
import CountUp from "./CountUp";
import Verdict from "./Verdict";

const inr = (n: number) => "₹" + Math.round(n).toLocaleString("en-IN");

export default function Results({ result }: { result: AnalyzeResult | null }) {
  return (
    <section id="results" className="px-6 py-16">
      <div className="mx-auto max-w-[1120px]">
        <div className="text-center text-[13px] font-extrabold uppercase tracking-[0.12em] text-sunset-orange">
          Your report
        </div>
        <h2 className="mt-2 text-center text-3xl font-extrabold tracking-tight">
          {result ? result.formatted_address : "Analyze an address to see your report"}
        </h2>

        {!result ? (
          <p className="mt-6 text-center text-sunset-muted">
            Enter your address above and we’ll measure your rooftop’s solar
            potential.
          </p>
        ) : (
          <div className="mt-10">
            <Verdict result={result} />
            {result.panel_count > 0 && <ResultCards result={result} />}
          </div>
        )}
      </div>
    </section>
  );
}

function ResultCards({ result }: { result: AnalyzeResult }) {
  const fin = result.financials!;
  const paybackPct = fin.payback_years
    ? Math.min(100, (fin.payback_years / 20) * 100)
    : 100;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="mt-10 grid gap-[18px] md:grid-cols-3"
    >
      {/* wide roof card */}
      <div className="relative col-span-full flex flex-col items-center gap-6 overflow-hidden rounded-[20px] border border-sunset-line bg-white p-6 shadow-[0_8px_26px_rgba(180,120,80,0.08)] md:flex-row">
        <img
          src={satelliteImageUrl({
            lat: result.coordinates.lat,
            lng: result.coordinates.lng,
          })}
          alt="Your rooftop"
          className="h-[180px] w-[280px] flex-shrink-0 rounded-[14px] border border-sunset-line object-cover"
        />
        <div className="flex-1">
          <div className="text-xs font-bold uppercase tracking-wider text-sunset-orange">
            Your rooftop
          </div>
          <div className="mt-2.5 text-3xl font-extrabold">
            {result.usable_area_m2}{" "}
            <span className="text-base font-semibold text-sunset-orange-lt">
              m² usable
            </span>
          </div>
          <div className="mt-2.5 text-[13px] text-[#a07a60]">
            {result.panel_count} panels · {result.system_size_kw} kW system ·{" "}
            {result.orientation} at {result.tilt}° tilt
          </div>
          <div className="mt-3.5 h-2.5 overflow-hidden rounded-full bg-sunset-line">
            <div
              className="h-full rounded-full bg-gradient-to-r from-sunset-orange to-sunset-green"
              style={{ width: `${paybackPct}%` }}
            />
          </div>
          <div className="mt-2 text-[13px] text-[#a07a60]">
            {fin.payback_years
              ? `Pays for itself in ~${fin.payback_years} years`
              : "Payback beyond 20 years at this consumption"}
          </div>
        </div>
      </div>

      <Card label="Annual generation" count={result.annual_kwh ?? 0} unit="kWh" note={`${result.specific_yield} kWh per kWp / year`} />
      <Card label="Yearly savings" count={fin.annual_savings} prefix="₹" note={`${inr(fin.monthly_savings)} / month off your bill`} highlight />
      <Card label="Net cost after subsidy" count={fin.net_cost_after_subsidy} prefix="₹" note={`${inr(fin.subsidy.total_subsidy)} subsidy applied`} />

      {result.monthly_kwh && <MonthlyChart monthly={result.monthly_kwh} />}
    </motion.div>
  );
}

function Card({
  label,
  count,
  prefix = "",
  unit,
  note,
  highlight,
}: {
  label: string;
  count: number;
  prefix?: string;
  unit?: string;
  note: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`relative overflow-hidden rounded-[20px] border bg-white p-6 shadow-[0_8px_26px_rgba(180,120,80,0.08)] ${
        highlight ? "border-[rgba(34,197,94,0.35)]" : "border-sunset-line"
      }`}
    >
      <div
        className="pointer-events-none absolute -right-10 -top-10 h-[110px] w-[110px] rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(255,196,87,0.30), transparent 70%)",
        }}
      />
      <div
        className={`text-xs font-bold uppercase tracking-wider ${
          highlight ? "text-sunset-green" : "text-sunset-orange"
        }`}
      >
        {label}
      </div>
      <div
        className={`mt-2.5 text-[38px] font-extrabold leading-none ${
          highlight ? "text-sunset-green" : "text-foreground"
        }`}
      >
        {prefix}
        <CountUp value={count} />
        {unit && (
          <span className="ml-1 text-base font-semibold text-sunset-orange-lt">
            {unit}
          </span>
        )}
      </div>
      <div className="mt-2.5 text-[13px] text-[#a07a60]">{note}</div>
    </div>
  );
}
