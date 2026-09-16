"""
India market configuration for the solar calculator.

IMPORTANT: Every block below has a `last_verified` date. These are policy
numbers that change over time (subsidy scheme revisions, DISCOM tariff
resets, bank rate changes). Re-check the source before trusting anything
older than ~6 months, and update `last_verified` when you do.

Sources are listed inline. This file intentionally contains NO calculation
logic — see financial_model.py for that. Keeping data and logic separate
means a policy update never requires touching (or re-testing) the math.
"""

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# 1. CENTRAL SUBSIDY — PM Surya Ghar Muft Bijli Yojana
# ---------------------------------------------------------------------------
# Structure is a FIXED SLAB by system size, not a percentage of cost.
# Residential grid-connected rooftop only. Capped at 3 kW — larger systems
# get zero additional subsidy for the kW beyond 3.
#
# Source: MNRE / pmsuryaghar.gov.in, PIB releases through mid-2026.
# Last verified: 2026-09-14

CENTRAL_SUBSIDY = {
    "rate_per_kw_first_2kw": 30_000,   # ₹ per kW, for kW 1 and 2
    "rate_per_kw_3rd_kw": 18_000,      # ₹ per kW, for kW 3 only
    "max_subsidy_kw": 3.0,             # no additional subsidy beyond this
    "max_subsidy_amount": 78_000,      # hard cap, ₹
    "eligible_connection_types": ["residential"],  # NOT commercial
    "requires_almm_listed_modules": True,
    "requires_mnre_empanelled_installer": True,
    "requires_discom_net_metering_signoff": True,
    "last_verified": "2026-09-14",
    "source": "https://pmsuryaghar.gov.in ; MNRE guidelines",
}


# ---------------------------------------------------------------------------
# 2. STATE TOP-UP SUBSIDIES
# ---------------------------------------------------------------------------
# Layered ON TOP of the central subsidy. Varies independently by state and
# changes on its own schedule — treat each entry as needing its own
# verification, not just the whole table at once.
#
# This list is illustrative / incomplete. Add states as you confirm them —
# do NOT assume "not listed" means "no top-up"; it may just mean unverified.

STATE_TOPUPS = {
    "Uttar Pradesh": {
        "amount_per_kw": 15_000,
        "max_kw": 2,          # confirm cap before relying on this
        "notes": "Additional to central subsidy; verify current scheme name.",
        "last_verified": "2026-09-14",
        "source": "State DISCOM / UPNEDA notification",
    },
    "Rajasthan": {
        "flat_amount": 17_000,
        "notes": "Subject to RREC / DISCOM conditions.",
        "last_verified": "2026-09-14",
        "source": "RREC notification",
    },
    # Bihar and others reported to have similar programs — NOT yet verified
    # with a primary source. Do not ship these as hardcoded numbers without
    # confirming amount + conditions from the state nodal agency.
}


# ---------------------------------------------------------------------------
# 3. DISCOM SLAB TARIFFS (illustrative sample — NOT exhaustive)
# ---------------------------------------------------------------------------
# Indian residential electricity billing is slab-based: different rates
# apply to different consumption bands within a billing cycle. This is a
# STARTER set for a few major cities/DISCOMs so the calculator doesn't
# assume a single flat ₹/kWh rate (which materially understates savings for
# high-consumption households and overstates it for low-consumption ones).
#
# Rates are ₹/kWh (unit). Replace/expand with your target markets' actual
# current tariff orders (published by each State Electricity Regulatory
# Commission, usually annually).

DISCOM_TARIFF_SLABS = {
    "Delhi (BSES/Tata Power, illustrative)": {
        "slabs": [
            (0, 200, 3.00),
            (201, 400, 4.50),
            (401, 800, 6.50),
            (801, 1200, 7.00),
            (1201, None, 8.00),  # None = no upper bound
        ],
        "fixed_charge_per_month": 20,  # ₹, simplified — real bills vary by load
        "last_verified": "2026-09-14",
        "source": "DERC tariff order (verify latest annual revision)",
    },
    "Maharashtra (MSEDCL, illustrative)": {
        "slabs": [
            (0, 100, 4.71),
            (101, 300, 9.61),
            (301, 500, 13.32),
            (501, None, 14.90),
        ],
        "fixed_charge_per_month": 30,
        "last_verified": "2026-09-14",
        "source": "MERC tariff order (verify latest annual revision)",
    },
    # Add Karnataka (BESCOM), Tamil Nadu (TANGEDCO), Gujarat (state DISCOMs),
    # etc. as needed for target markets. Treat every number here as a
    # placeholder until cross-checked against the current tariff order.
}


# ---------------------------------------------------------------------------
# 4. NET METERING POLICY (varies by state — this is a simplified switch)
# ---------------------------------------------------------------------------
# "net" = excess export offsets future consumption at retail rate (banked,
#         with an expiry — commonly annual settlement).
# "gross" = ALL generation is sold to the DISCOM at a separate (usually
#         lower) feed-in tariff, and ALL consumption is billed normally.
# Some states apply "net" only below a size threshold and "gross" above it.

NET_METERING_POLICY = {
    "Delhi": {
        "type": "net",
        "banking_period_months": 12,
        "feed_in_tariff_inr_per_kwh": None,  # not applicable under net metering
        "last_verified": "2026-09-14",
        "source": "DERC net metering regulations",
    },
    "Maharashtra": {
        "type": "net",
        "banking_period_months": 12,
        "feed_in_tariff_inr_per_kwh": None,
        "last_verified": "2026-09-14",
        "source": "MERC net metering regulations",
    },
    # Where gross metering applies above a size threshold, model it as:
    # {"type": "gross", "feed_in_tariff_inr_per_kwh": <rate>, ...}
}


# ---------------------------------------------------------------------------
# 5. SOLAR LOAN PRODUCTS (for EMI-vs-cash payback comparison)
# ---------------------------------------------------------------------------
# Floating rates — these move. Treat as indicative only; always tell the
# user to confirm the live rate before financing a decision on it.

LOAN_PRODUCTS = {
    "SBI Surya Ghar Loan": {
        "rate_upto_2_lakh": 5.75,   # % p.a., floating
        "rate_2_to_6_lakh": 7.90,   # % p.a., floating
        "collateral_free": True,
        "last_verified": "2026-09-14",
        "source": "SBI official rate card (verify current rate before quoting)",
    },
}


@dataclass
class SystemSpec:
    """Minimal system description needed to run the financial model."""
    size_kw: float
    state: str
    discom_key: Optional[str] = None      # key into DISCOM_TARIFF_SLABS
    connection_type: str = "residential"  # "residential" | "commercial"
    monthly_consumption_kwh: float = 300.0
