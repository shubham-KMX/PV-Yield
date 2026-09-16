/**
 * API client for the PV-Yield backend.
 *
 * One place that knows how to talk to the FastAPI backend — the frontend
 * mirror of the clean "service" pattern used on the Python side. Components
 * import these functions/types instead of calling fetch() directly.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---- types mirroring the backend /analyze response ------------------------

export interface Subsidy {
  central_subsidy: number;
  state_topup: number;
  total_subsidy: number;
}

export interface Financials {
  system_cost: number;
  subsidy: Subsidy;
  net_cost_after_subsidy: number;
  monthly_savings: number;
  annual_savings: number;
  payback_years: number | null;
  lifetime_savings: number;
  loan_emi_monthly: number;
  loan_rate_pct: number;
  cost_per_watt: number;
}

export interface AnalyzeResult {
  success: boolean;
  coordinates: { lat: number; lng: number };
  formatted_address: string;
  roof_area_m2: number;
  // Present only when panels fit:
  usable_area_m2?: number;
  panel_count: number;
  system_size_kw?: number;
  orientation?: string;
  annual_kwh?: number;
  monthly_kwh?: Record<string, number>;
  specific_yield?: number;
  tilt?: number;
  financials?: Financials;
  image_source?: string;
  message?: string; // e.g. "No panels fit..."
}

export interface AnalyzeRequest {
  address?: string;
  lat?: number;
  lng?: number;
  points?: [number, number][];
  polygon?: [number, number][];
  auto_expand?: boolean;
  apply_shading?: boolean;
  state?: string;
  discom_key?: string;
  monthly_consumption_kwh?: number;
}

// ---- the call --------------------------------------------------------------

/**
 * Run the full analysis for an address (or coordinates / roof selection).
 * Throws an Error with the backend's message on failure.
 */
export async function analyze(req: AnalyzeRequest): Promise<AnalyzeResult> {
  const res = await fetch(`${API_URL}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    // FastAPI puts error text under { detail: "..." }.
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body; keep the generic message */
    }
    throw new Error(detail);
  }

  return res.json();
}

export interface GeocodeResult {
  lat: number;
  lng: number;
  formatted_address: string;
}

/** Geocode an address to coordinates (used before showing the roof image). */
export async function geocode(address: string): Promise<GeocodeResult> {
  const res = await fetch(
    `${API_URL}/geocode?address=${encodeURIComponent(address)}`,
  );
  if (!res.ok) {
    let detail = `Geocoding failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* keep generic */
    }
    throw new Error(detail);
  }
  return res.json();
}

/** URL of the satellite image for a location (served by the backend). */
export function satelliteImageUrl(params: {
  address?: string;
  lat?: number;
  lng?: number;
}): string {
  const q = new URLSearchParams();
  if (params.address) q.set("address", params.address);
  if (params.lat !== undefined) q.set("lat", String(params.lat));
  if (params.lng !== undefined) q.set("lng", String(params.lng));
  return `${API_URL}/satellite?${q.toString()}`;
}
