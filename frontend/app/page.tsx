"use client";

/**
 * Home page — composes the whole landing experience.
 *
 * Holds the shared analysis `result`: the Hero produces it (on submit),
 * the Results section consumes it. This "lift state up" pattern is the
 * standard React way to share data between sibling components.
 */
import { useState } from "react";

import Header from "./components/Header";
import Hero from "./components/Hero";
import HowItWorks from "./components/HowItWorks";
import Results from "./components/Results";
import Footer from "./components/Footer";
import type { AnalyzeResult } from "@/lib/api";

export default function Home() {
  const [result, setResult] = useState<AnalyzeResult | null>(null);

  return (
    <>
      <Header />
      <main className="flex-1">
        <Hero onResult={setResult} />
        <HowItWorks />
        <Results result={result} />
      </main>
      <Footer />
    </>
  );
}
