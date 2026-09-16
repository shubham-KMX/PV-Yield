"use client";

/**
 * MonthlyChart — a sunset-styled bar chart of monthly generation (kWh),
 * built from the backend's `monthly_kwh` map. Shows the seasonal shape of
 * a year's solar output.
 */
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const MONTH_ORDER = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export default function MonthlyChart({
  monthly,
}: {
  monthly: Record<string, number>;
}) {
  // Keep months in calendar order and drop any that are missing.
  const data = MONTH_ORDER.filter((m) => m in monthly).map((m) => ({
    month: m,
    kwh: Math.round(monthly[m]),
  }));

  const peak = Math.max(...data.map((d) => d.kwh));

  return (
    <div className="col-span-full rounded-[20px] border border-sunset-line bg-white p-6 shadow-[0_8px_26px_rgba(180,120,80,0.08)]">
      <div className="mb-1 text-xs font-bold uppercase tracking-wider text-sunset-orange">
        Monthly generation
      </div>
      <div className="mb-4 text-[13px] text-[#a07a60]">
        Estimated kWh produced each month across the year
      </div>

      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <defs>
            <linearGradient id="sunsetBar" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ffc457" />
              <stop offset="100%" stopColor="#f97316" />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#f2e6da" vertical={false} />
          <XAxis
            dataKey="month"
            tick={{ fill: "#a07a60", fontSize: 12 }}
            axisLine={{ stroke: "#f2e6da" }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#a07a60", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: "rgba(249,115,22,0.06)" }}
            contentStyle={{
              borderRadius: 12,
              border: "1px solid #f2e6da",
              boxShadow: "0 8px 24px rgba(180,120,80,0.15)",
            }}
            formatter={(v) => [`${Number(v).toLocaleString("en-IN")} kWh`, "Generation"]}
          />
          <Bar dataKey="kwh" radius={[6, 6, 0, 0]}>
            {data.map((d) => (
              <Cell
                key={d.month}
                // The peak month glows brighter to draw the eye.
                fill={d.kwh === peak ? "#f97316" : "url(#sunsetBar)"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
