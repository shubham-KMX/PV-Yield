"use client";

/**
 * Home page — orchestrates the three-stage flow:
 *
 *   1. "search"  : user enters an address (Hero)
 *   2. "select"  : we show the satellite image; user marks their roof
 *   3. "results" : full analysis for the chosen selection
 *
 * The page owns the shared state (coordinates + result) and moves between
 * stages. Children stay focused: Hero collects the address, RoofSelector
 * captures the roof, Results renders the report.
 */
import { useState } from "react";

import Header from "./components/Header";
import Hero from "./components/Hero";
import HowItWorks from "./components/HowItWorks";
import RoofSelector from "./components/RoofSelector";
import AnalysisOptions, {
  type FinanceOptions,
  SUPPORTED_STATES,
} from "./components/AnalysisOptions";
import Results from "./components/Results";
import ResultsSkeleton from "./components/ResultsSkeleton";
import Footer from "./components/Footer";
import { analyze, type AnalyzeResult } from "@/lib/api";

type Pt = [number, number];

export default function Home() {
  const [coords, setCoords] = useState<{ lat: number; lng: number; address: string } | null>(null);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [finance, setFinance] = useState<FinanceOptions>({
    state: SUPPORTED_STATES[0].state,
    discom_key: SUPPORTED_STATES[0].discom_key,
    monthly_consumption_kwh: 300,
    tilt: null,
    azimuth: null,
  });

  // Stage 1 -> 2: address geocoded, show the roof selector.
  function handleGeocoded(lat: number, lng: number, address: string) {
    setCoords({ lat, lng, address });
    setResult(null);
    setError(null);
    setTimeout(
      () => document.getElementById("select")?.scrollIntoView({ behavior: "smooth" }),
      50,
    );
  }

  // Stage 2 -> 3: run the full analysis with the chosen roof selection.
  async function handleSelection(sel: { points?: Pt[]; polygon?: Pt[] }) {
    if (!coords) return;
    setAnalyzing(true);
    setError(null);
    try {
      const r = await analyze({
        lat: coords.lat,
        lng: coords.lng,
        points: sel.points,
        polygon: sel.polygon,
        state: finance.state,
        discom_key: finance.discom_key,
        monthly_consumption_kwh: finance.monthly_consumption_kwh,
        tilt: finance.tilt,
        azimuth: finance.azimuth,
      });
      setResult(r);
      setTimeout(
        () => document.getElementById("results")?.scrollIntoView({ behavior: "smooth" }),
        50,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed.");
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <>
      <div className="no-print">
        <Header />
      </div>
      <main className="flex-1">
        <div className="no-print">
          <Hero onGeocoded={handleGeocoded} />
        </div>

        {coords && (
          <section id="select" className="no-print border-t border-sunset-line px-6 py-16">
            <div className="mx-auto max-w-[1120px]">
              <div className="text-center text-[13px] font-extrabold uppercase tracking-[0.12em] text-sunset-orange">
                Step 2 · Mark your roof
              </div>
              <h2 className="mb-8 mt-2 text-center text-3xl font-extrabold tracking-tight">
                Which rooftop is yours?
              </h2>
              <RoofSelector
                key={`${coords.lat},${coords.lng}`}
                lat={coords.lat}
                lng={coords.lng}
                onAnalyze={handleSelection}
                loading={analyzing}
              />
              <AnalysisOptions value={finance} onChange={setFinance} />
              {error && (
                <p className="mt-4 text-center text-sm font-medium text-sunset-coral">
                  {error}
                </p>
              )}
            </div>
          </section>
        )}

        <div className="no-print">
          <HowItWorks />
        </div>
        {analyzing ? (
          <section className="no-print px-6 py-16">
            <div className="mx-auto max-w-[1120px] text-center text-[13px] font-extrabold uppercase tracking-[0.12em] text-sunset-orange">
              Crunching the numbers…
            </div>
            <ResultsSkeleton />
          </section>
        ) : (
          <Results result={result} />
        )}
      </main>
      <div className="no-print">
        <Footer />
      </div>
    </>
  );
}
