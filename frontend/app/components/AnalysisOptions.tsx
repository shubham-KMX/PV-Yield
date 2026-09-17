"use client";

/**
 * AnalysisOptions — the consumption + location inputs the financial model
 * needs. Without these, savings/payback are computed against a hardcoded
 * default and can look wrong for large systems.
 *
 * We only offer states the backend actually has tariff + net-metering data
 * for (picking an unconfigured state would error on the backend).
 */
import { Zap, MapPin, Compass, Triangle } from "lucide-react";

// Each supported state maps to its DISCOM tariff key in the backend.
export const SUPPORTED_STATES: { state: string; discom_key: string }[] = [
  { state: "Delhi", discom_key: "Delhi (BSES/Tata Power, illustrative)" },
  { state: "Maharashtra", discom_key: "Maharashtra (MSEDCL, illustrative)" },
];

export interface FinanceOptions {
  state: string;
  discom_key: string;
  monthly_consumption_kwh: number;
  // null = let the backend decide (latitude tilt / footprint azimuth).
  tilt: number | null;
  azimuth: number | null;
}

interface Props {
  value: FinanceOptions;
  onChange: (v: FinanceOptions) => void;
}

export default function AnalysisOptions({ value, onChange }: Props) {
  return (
    <div className="mx-auto mt-6 grid max-w-[560px] gap-4 rounded-2xl border border-sunset-line bg-white p-5 shadow-[0_6px_20px_rgba(180,120,80,0.06)] sm:grid-cols-2">
      {/* monthly consumption */}
      <div>
        <label className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-foreground">
          <Zap className="h-4 w-4 text-sunset-orange" />
          Monthly usage
          <span className="ml-auto font-bold text-sunset-orange">
            {value.monthly_consumption_kwh} kWh
          </span>
        </label>
        <input
          type="range"
          min={50}
          max={2000}
          step={50}
          value={value.monthly_consumption_kwh}
          onChange={(e) =>
            onChange({ ...value, monthly_consumption_kwh: Number(e.target.value) })
          }
          className="w-full accent-sunset-orange"
        />
        <div className="mt-1 flex justify-between text-[11px] text-sunset-muted">
          <span>50</span>
          <span>2000</span>
        </div>
      </div>

      {/* state */}
      <div>
        <label className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-foreground">
          <MapPin className="h-4 w-4 text-sunset-orange" />
          State
        </label>
        <select
          value={value.state}
          onChange={(e) => {
            const found = SUPPORTED_STATES.find((s) => s.state === e.target.value)!;
            onChange({
              ...value,
              state: found.state,
              discom_key: found.discom_key,
            });
          }}
          className="w-full rounded-xl border border-sunset-line bg-white px-3 py-2.5 text-sm text-foreground outline-none focus:border-sunset-orange"
        >
          {SUPPORTED_STATES.map((s) => (
            <option key={s.state} value={s.state}>
              {s.state}
            </option>
          ))}
        </select>
        <p className="mt-1 text-[11px] text-sunset-muted">
          Sets the electricity tariff &amp; net-metering rules.
        </p>
      </div>

      {/* --- panel angle (optional overrides) --- */}
      <div className="sm:col-span-2 border-t border-sunset-line pt-4">
        <div className="mb-3 text-xs font-bold uppercase tracking-wider text-sunset-muted">
          Panel angle (optional — we estimate these for you)
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {/* tilt */}
          <div>
            <label className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
              <Triangle className="h-4 w-4 text-sunset-orange" />
              Tilt
              <span className="ml-auto text-sunset-orange">
                {value.tilt === null ? "Auto" : `${value.tilt}°`}
              </span>
            </label>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={value.tilt !== null}
                onChange={(e) =>
                  onChange({ ...value, tilt: e.target.checked ? 20 : null })
                }
                className="accent-sunset-orange"
              />
              <input
                type="range"
                min={5}
                max={45}
                step={1}
                disabled={value.tilt === null}
                value={value.tilt ?? 20}
                onChange={(e) => onChange({ ...value, tilt: Number(e.target.value) })}
                className="w-full accent-sunset-orange disabled:opacity-40"
              />
            </div>
          </div>

          {/* azimuth */}
          <div>
            <label className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
              <Compass className="h-4 w-4 text-sunset-orange" />
              Facing
              <span className="ml-auto text-sunset-orange">
                {value.azimuth === null ? "Auto" : `${value.azimuth}°`}
              </span>
            </label>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={value.azimuth !== null}
                onChange={(e) =>
                  onChange({ ...value, azimuth: e.target.checked ? 180 : null })
                }
                className="accent-sunset-orange"
              />
              <input
                type="range"
                min={90}
                max={270}
                step={5}
                disabled={value.azimuth === null}
                value={value.azimuth ?? 180}
                onChange={(e) => onChange({ ...value, azimuth: Number(e.target.value) })}
                className="w-full accent-sunset-orange disabled:opacity-40"
              />
            </div>
            <p className="mt-1 text-[11px] text-sunset-muted">
              90 = East · 180 = South · 270 = West
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
