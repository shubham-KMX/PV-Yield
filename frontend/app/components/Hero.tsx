"use client";

/**
 * Hero section: the glowing sun, headline, and the address search that
 * kicks off a full analysis against the backend.
 *
 * "use client" because it holds form state and does a fetch on submit.
 */
import { useState } from "react";
import { Sun, Loader2 } from "lucide-react";
import { geocode } from "@/lib/api";

interface HeroProps {
  // Called once the address is geocoded; the page then shows the roof selector.
  onGeocoded: (lat: number, lng: number, address: string) => void;
}

export default function Hero({ onGeocoded }: HeroProps) {
  const [address, setAddress] = useState("E-87, Sarita Vihar, New Delhi");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAnalyze() {
    if (!address.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      // Geocode only — the heavy analysis runs after the user marks the roof.
      const geo = await geocode(address.trim());
      onGeocoded(geo.lat, geo.lng, geo.formatted_address);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div id="analyze" className="relative overflow-hidden px-6 py-[70px] text-center">
      {/* soft sunset glow behind the hero */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(80% 60% at 50% -10%, rgba(255,196,87,0.35), rgba(255,157,92,0.14) 45%, transparent 75%)",
        }}
      />

      <div className="relative mx-auto max-w-[1120px]">
        <div className="sun-orb mx-auto mb-6 h-[92px] w-[92px]" />

        <span className="mb-[22px] inline-block rounded-full border border-[rgba(249,115,22,0.25)] bg-[rgba(249,115,22,0.1)] px-3.5 py-1.5 text-xs font-bold uppercase tracking-wide text-sunset-orange">
          Rooftop solar, measured not guessed
        </span>

        <h1 className="text-[54px] font-extrabold leading-[1.05] tracking-[-1.5px]">
          Know what your roof can
          <br />
          <span className="text-sunset-gradient">earn from the sun</span>
        </h1>

        <p className="mx-auto mt-[18px] max-w-[560px] text-lg leading-relaxed text-sunset-muted">
          Enter your address and get a real solar feasibility report — roof
          area, panel count, yearly generation and savings — in seconds.
        </p>

        {/* search */}
        <div className="relative z-[1] mx-auto mt-8 flex max-w-[620px] gap-2.5 rounded-2xl border border-sunset-line bg-white p-2 shadow-[0_14px_44px_rgba(249,115,22,0.14)]">
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAnalyze()}
            placeholder="Enter your address…"
            className="flex-1 bg-transparent px-4 py-3.5 text-base text-foreground outline-none placeholder:text-[#bfa694]"
          />
          <button
            onClick={handleAnalyze}
            disabled={loading}
            className="flex items-center gap-2 whitespace-nowrap rounded-xl bg-gradient-to-br from-sunset-orange-lt to-sunset-orange px-[26px] py-3.5 text-[15px] font-bold text-white shadow-[0_6px_20px_rgba(249,115,22,0.4)] transition-transform hover:scale-[1.02] disabled:opacity-70"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Analyzing…
              </>
            ) : (
              <>
                Find my roof <Sun className="h-4 w-4" />
              </>
            )}
          </button>
        </div>

        {error && (
          <p className="relative z-[1] mt-3 text-sm font-medium text-sunset-coral">
            {error}
          </p>
        )}

        <p className="relative z-[1] mt-[18px] text-[13px] text-[#b89a85]">
          Powered by satellite imagery · NASA weather data · NREL solar physics
        </p>
      </div>
    </div>
  );
}
