"""
India-specific financial model for the solar calculator.

All calculation logic lives here. All policy numbers live in
market_config.py. Never hardcode a ₹ figure or a rate in this file —
if a number isn't in the config yet, add it there with a source and a
last_verified date, then reference it from here.
"""

from typing import Optional

from app.services.finance.market_config import (
    CENTRAL_SUBSIDY,
    STATE_TOPUPS,
    DISCOM_TARIFF_SLABS,
    NET_METERING_POLICY,
    LOAN_PRODUCTS,
    SystemSpec,
)


# ---------------------------------------------------------------------------
# 1. Subsidy
# ---------------------------------------------------------------------------

def central_subsidy(system_kw: float, connection_type: str = "residential") -> float:
    """
    PM Surya Ghar central subsidy: fixed slab, capped at 3 kW.
    Returns 0 for commercial connections (not eligible).
    """
    cfg = CENTRAL_SUBSIDY
    if connection_type not in cfg["eligible_connection_types"]:
        return 0.0

    # Subsidy is calculated on capacity up to the cap, not the full system
    # size — a 6 kW system still only gets the 3 kW-worth of subsidy.
    capped_kw = min(system_kw, cfg["max_subsidy_kw"])

    first_2kw = min(capped_kw, 2.0)
    third_kw = max(0.0, capped_kw - 2.0)

    amount = (
        first_2kw * cfg["rate_per_kw_first_2kw"]
        + third_kw * cfg["rate_per_kw_3rd_kw"]
    )
    return min(amount, cfg["max_subsidy_amount"])


def state_topup(system_kw: float, state: str) -> float:
    """
    State top-up subsidy on top of the central amount. Returns 0 if the
    state has no verified entry — this is a deliberate fail-safe: we'd
    rather under-promise than quote an unverified number to a customer.
    """
    entry = STATE_TOPUPS.get(state)
    if entry is None:
        return 0.0

    if "flat_amount" in entry:
        return entry["flat_amount"]

    if "amount_per_kw" in entry:
        capped_kw = min(system_kw, entry.get("max_kw", system_kw))
        return capped_kw * entry["amount_per_kw"]

    return 0.0


def total_subsidy(system_kw: float, state: str, connection_type: str = "residential") -> dict:
    """Returns a breakdown, not just a total — useful for showing the
    customer exactly where the number comes from."""
    central = central_subsidy(system_kw, connection_type)
    state_amt = state_topup(system_kw, state)
    return {
        "central_subsidy": central,
        "state_topup": state_amt,
        "total_subsidy": central + state_amt,
    }


# ---------------------------------------------------------------------------
# 2. Slab-based electricity billing
# ---------------------------------------------------------------------------

def slab_bill(units_kwh: float, discom_key: str) -> float:
    """
    Computes a monthly bill from a slab tariff structure.
    Raises KeyError if discom_key isn't in the config — fail loudly rather
    than silently defaulting to a flat rate that misrepresents the DISCOM.
    """
    if discom_key not in DISCOM_TARIFF_SLABS:
        raise KeyError(
            f"No tariff slab on file for '{discom_key}'. "
            f"Add it to DISCOM_TARIFF_SLABS in market_config.py "
            f"before billing this DISCOM."
        )

    cfg = DISCOM_TARIFF_SLABS[discom_key]
    remaining = units_kwh
    cost = cfg["fixed_charge_per_month"]

    for lower, upper, rate in cfg["slabs"]:
        if remaining <= 0:
            break
        band_size = (upper - lower + 1) if upper is not None else remaining
        units_in_band = min(remaining, band_size)
        cost += units_in_band * rate
        remaining -= units_in_band

    return round(cost, 2)


# ---------------------------------------------------------------------------
# 3. Net metering savings
# ---------------------------------------------------------------------------

def monthly_net_metering_savings(
    monthly_generation_kwh: float,
    monthly_consumption_kwh: float,
    state: str,
    discom_key: str,
) -> dict:
    """
    Compares the bill WITH solar (net of export credit) against the bill
    WITHOUT solar, under the state's net/gross metering policy.

    Note: this is a single-month simplification. Real net-metering banking
    carries credit across a settlement period (commonly annual) — for a
    proper multi-month simulation, track a running credit balance across
    calls to this function rather than resetting each month.
    """
    policy = NET_METERING_POLICY.get(state)
    if policy is None:
        raise KeyError(
            f"No net metering policy on file for '{state}'. "
            f"Add it to NET_METERING_POLICY before modeling savings there."
        )

    bill_without_solar = slab_bill(monthly_consumption_kwh, discom_key)

    if policy["type"] == "net":
        net_units = max(0.0, monthly_consumption_kwh - monthly_generation_kwh)
        bill_with_solar = slab_bill(net_units, discom_key) if net_units > 0 else 0.0
        exported_units_banked = max(0.0, monthly_generation_kwh - monthly_consumption_kwh)
        savings = bill_without_solar - bill_with_solar
        return {
            "bill_without_solar": bill_without_solar,
            "bill_with_solar": bill_with_solar,
            "monthly_savings": round(savings, 2),
            "exported_units_banked": round(exported_units_banked, 2),
            "metering_type": "net",
        }

    elif policy["type"] == "gross":
        feed_in_rate = policy["feed_in_tariff_inr_per_kwh"]
        export_earnings = monthly_generation_kwh * feed_in_rate
        savings = export_earnings  # consumption is billed separately in full
        return {
            "bill_without_solar": bill_without_solar,
            "bill_with_solar": bill_without_solar,  # billed in full regardless
            "export_earnings": round(export_earnings, 2),
            "monthly_savings": round(savings, 2),
            "metering_type": "gross",
        }

    raise ValueError(f"Unknown metering type in policy: {policy['type']}")


# ---------------------------------------------------------------------------
# 4. Loan EMI
# ---------------------------------------------------------------------------

def emi(principal: float, annual_rate_pct: float, tenure_years: float) -> float:
    """Standard reducing-balance EMI formula."""
    r = (annual_rate_pct / 100) / 12  # monthly rate
    n = tenure_years * 12
    if r == 0:
        return principal / n
    return round(principal * r * (1 + r) ** n / ((1 + r) ** n - 1), 2)


def loan_rate_for_amount(loan_product: str, principal: float) -> float:
    cfg = LOAN_PRODUCTS[loan_product]
    if principal <= 200_000:
        return cfg["rate_upto_2_lakh"]
    return cfg["rate_2_to_6_lakh"]


# ---------------------------------------------------------------------------
# 5. Payback period (with degradation)
# ---------------------------------------------------------------------------

def payback_and_lifetime_savings(
    system_cost: float,
    subsidy: float,
    annual_savings_year1: float,
    degradation_rate_pct: float = 0.5,
    years: int = 20,
) -> dict:
    """
    Simple payback: net cost after subsidy, divided against savings that
    shrink slightly each year as panel output degrades.
    Does NOT model electricity tariff inflation — add that as a separate
    multiplier if you want a more aggressive (and more speculative) number.
    """
    net_cost = system_cost - subsidy
    cumulative = 0.0
    payback_year: Optional[float] = None
    yearly_savings = []

    for year in range(1, years + 1):
        year_savings = annual_savings_year1 * (1 - degradation_rate_pct / 100) ** (year - 1)
        yearly_savings.append(round(year_savings, 2))
        cumulative += year_savings
        if payback_year is None and cumulative >= net_cost:
            # Linear interpolation within the year for a smoother estimate
            prev_cumulative = cumulative - year_savings
            fraction = (net_cost - prev_cumulative) / year_savings
            payback_year = round((year - 1) + fraction, 2)

    return {
        "net_cost_after_subsidy": net_cost,
        "payback_years": payback_year,  # None if never pays back within `years`
        "lifetime_savings": round(cumulative, 2),
        "yearly_savings": yearly_savings,
    }
