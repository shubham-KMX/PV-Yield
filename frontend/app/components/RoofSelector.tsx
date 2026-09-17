"use client";

/**
 * RoofSelector — shows the satellite image and lets the user mark their
 * roof, either by clicking points or drawing a polygon outline.
 *
 * Coordinate mapping: the backend serves a 1280x1280 native image but we
 * display it smaller. Every click is captured in DISPLAY pixels and scaled
 * back to NATIVE pixels (× 1280/displayWidth) before we hand it to the
 * backend, which reasons in native pixels.
 */
import { useRef, useState } from "react";
import { MousePointerClick, Pencil, RotateCcw, Sparkles } from "lucide-react";
import { satelliteImageUrl } from "@/lib/api";

const NATIVE_SIZE = 1280; // px, the backend's satellite image dimension
const DISPLAY_SIZE = 560; // px, how big we render it

type Mode = "points" | "polygon";
type Pt = [number, number]; // native-pixel coordinates

interface RoofSelectorProps {
  lat: number;
  lng: number;
  onAnalyze: (selection: { points?: Pt[]; polygon?: Pt[] }) => void;
  loading?: boolean;
}

export default function RoofSelector({
  lat,
  lng,
  onAnalyze,
  loading,
}: RoofSelectorProps) {
  const [mode, setMode] = useState<Mode>("points");
  const [marks, setMarks] = useState<Pt[]>([]); // native-pixel coords
  const imgRef = useRef<HTMLImageElement>(null);
  // Note: markers reset automatically when the location changes, because
  // the parent gives this component a `key` tied to lat/lng, which remounts
  // it fresh. (Cleaner than resetting state inside an effect.)

  // Convert a click on the displayed image into NATIVE pixel coords.
  function handleClick(e: React.MouseEvent<HTMLDivElement>) {
    if (loading) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const dx = e.clientX - rect.left; // display px
    const dy = e.clientY - rect.top;
    const scale = NATIVE_SIZE / rect.width;
    const nx = Math.round(dx * scale);
    const ny = Math.round(dy * scale);
    setMarks((prev) => [...prev, [nx, ny]]);
  }

  // Back to display px for drawing the markers on top of the image.
  const toDisplay = ([nx, ny]: Pt): [number, number] => {
    const s = DISPLAY_SIZE / NATIVE_SIZE;
    return [nx * s, ny * s];
  };

  function analyze() {
    if (marks.length === 0) return;
    if (mode === "polygon") onAnalyze({ polygon: marks });
    else onAnalyze({ points: marks });
  }

  return (
    <div className="mx-auto max-w-[620px]">
      {/* mode toggle */}
      <div className="mb-3 flex items-center justify-center gap-2">
        <ModeButton active={mode === "points"} onClick={() => { setMode("points"); setMarks([]); }} icon={MousePointerClick} label="Click roof" />
        <ModeButton active={mode === "polygon"} onClick={() => { setMode("polygon"); setMarks([]); }} icon={Pencil} label="Draw outline" />
      </div>

      <p className="mb-3 text-center text-sm text-sunset-muted">
        {mode === "points"
          ? "Click one or more points on your rooftop."
          : "Click around your roof’s edge to trace its outline (3+ points)."}
      </p>

      {/* the image + click layer */}
      <div
        onClick={handleClick}
        className="relative mx-auto cursor-crosshair overflow-hidden rounded-2xl border border-sunset-line shadow-[0_10px_30px_rgba(180,120,80,0.15)]"
        style={{ width: DISPLAY_SIZE, height: DISPLAY_SIZE }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          ref={imgRef}
          src={satelliteImageUrl({ lat, lng })}
          alt="Your rooftop"
          width={DISPLAY_SIZE}
          height={DISPLAY_SIZE}
          className="block select-none"
          draggable={false}
        />

        {/* polygon outline */}
        {mode === "polygon" && marks.length > 1 && (
          <svg
            className="pointer-events-none absolute inset-0"
            width={DISPLAY_SIZE}
            height={DISPLAY_SIZE}
          >
            <polygon
              points={marks.map(toDisplay).map(([x, y]) => `${x},${y}`).join(" ")}
              fill="rgba(249,115,22,0.25)"
              stroke="#f97316"
              strokeWidth={2}
            />
          </svg>
        )}

        {/* click markers */}
        {marks.map((m, i) => {
          const [x, y] = toDisplay(m);
          return (
            <span
              key={i}
              className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-sunset-orange shadow"
              style={{ left: x, top: y }}
            />
          );
        })}
      </div>

      {/* actions */}
      <div className="mt-4 flex items-center justify-center gap-2.5">
        <button
          onClick={() => setMarks([])}
          disabled={marks.length === 0 || loading}
          className="flex items-center gap-1.5 rounded-xl border border-sunset-line bg-white px-4 py-2.5 text-sm font-semibold text-sunset-muted transition-colors hover:text-sunset-orange disabled:opacity-50"
        >
          <RotateCcw className="h-4 w-4" /> Clear
        </button>
        <button
          onClick={analyze}
          disabled={
            loading ||
            marks.length === 0 ||
            (mode === "polygon" && marks.length < 3)
          }
          className="rounded-xl bg-gradient-to-br from-sunset-orange-lt to-sunset-orange px-6 py-2.5 text-sm font-bold text-white shadow-[0_6px_20px_rgba(249,115,22,0.4)] transition-transform hover:scale-[1.02] disabled:opacity-50"
        >
          {loading ? "Analyzing…" : `Analyze this ${mode === "polygon" ? "outline" : "selection"}`}
        </button>
        <button
          onClick={() => onAnalyze({})}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-xl border border-sunset-line bg-white px-4 py-2.5 text-sm font-semibold text-sunset-muted transition-colors hover:text-sunset-orange disabled:opacity-50"
          title="Let us auto-detect your roof"
        >
          <Sparkles className="h-4 w-4" /> Auto-detect
        </button>
      </div>
    </div>
  );
}

function ModeButton({
  active,
  onClick,
  icon: Icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ElementType;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors ${
        active
          ? "bg-sunset-orange text-white"
          : "border border-sunset-line bg-white text-sunset-muted hover:text-sunset-orange"
      }`}
    >
      <Icon className="h-4 w-4" /> {label}
    </button>
  );
}
