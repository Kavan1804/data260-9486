"""HW7 Part 4: read the Bay Wheels price table from the page text and compute the cost comparison.

parse_pricing(text) reads the "Compare your options" table of the pricing page:
  plan price row      $1.00 | $15/day | $29/month | $165/year | $199/year
  "Classic bike prices" row, then "Ebike prices" row (one value per plan, same order)
and returns the pay-per-use (single ride) and Month pass terms for each bike type.

cost_breakdown() computes every number with the Part 4 tools (csv_sql for the trip aggregates,
calculator for the arithmetic) and returns the tool calls it made, so the UI timeline shows them.

Assumptions (also shown in the UI):
  * per-minute charges are billed per started minute (duration rounded up)
  * the Month pass is bought for every calendar month that has at least one ride
  * the page does not list a Month-pass unlock fee for classic bikes; the Lyft Bike member text says
    "$0 unlocks", so classic unlocks are treated as $0 for pass holders
"""

from __future__ import annotations

import re

from .tools import calculator, csv_sql

PRICE_RE = re.compile(r"^\$(\d+(?:\.\d+)?)(/day|/month|/year)?$")
MONEY = re.compile(r"\$(\d+(?:\.\d+)?)")


def parse_rate(text: str) -> dict:
    """'$1.00 to unlock, then $0.19/min' -> {unlock: 1.0, included_min: 0, per_min: 0.19}."""
    low = text.lower()
    per_min = re.search(r"\$(\d+(?:\.\d+)?)/min", low)
    unlock = re.search(r"\$(\d+(?:\.\d+)?)\s*(?:to unlock|unlock)", low)
    included = re.search(r"(\d+)\s*min free", low)
    return {
        "unlock": float(unlock.group(1)) if unlock else 0.0,
        "included_min": int(included.group(1)) if included else 0,
        "per_min": float(per_min.group(1)) if per_min else 0.0,
        "text": text,
    }


def parse_pricing(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    start = next((i for i, line in enumerate(lines) if "compare your options" in line.lower()), 0)
    prices = []
    for line in lines[start:]:
        m = PRICE_RE.match(line)
        if m:
            prices.append((float(m.group(1)), m.group(2) or "/ride", line))
        elif prices and line.lower().startswith("get "):
            break
    n = len(prices)
    if n < 3:
        raise ValueError("could not find the plan price row on the pricing page")
    month_idx = next((i for i, p in enumerate(prices) if p[1] == "/month"), None)
    ride_idx = next((i for i, p in enumerate(prices) if p[1] == "/ride"), None)
    if month_idx is None or ride_idx is None:
        raise ValueError("pricing page has no Month pass or no single-ride price")

    def row(label: str) -> list[str]:
        i = next(i for i, line in enumerate(lines) if line.lower().startswith(label) and i > start)
        return lines[i + 1 : i + 1 + n]

    classic, ebike = row("classic bike prices"), row("ebike prices")
    return {
        "month_pass_price": prices[month_idx][0],
        "month_pass_price_text": prices[month_idx][2],
        "single_ride_price_text": prices[ride_idx][2],
        "pay_per_use": {"classic_bike": parse_rate(classic[ride_idx]), "electric_bike": parse_rate(ebike[ride_idx])},
        "month_pass": {"classic_bike": parse_rate(classic[month_idx]), "electric_bike": parse_rate(ebike[month_idx])},
    }


def _calc(expr: str, units: str, calls: list) -> float:
    r = calculator(expr, units)
    calls.append({"tool": "calculator", "input": {"expression": expr, "units": units}, "output": r})
    if not r["success"]:
        raise ValueError(r["error"])
    return r["data"]["value"]


def _sql(store, sql: str, calls: list) -> list[dict]:
    r = csv_sql(store, sql)
    calls.append(
        {
            "tool": "csv_sql",
            "input": {"sql": sql},
            "output": {**r, "data": {**(r["data"] or {}), "rows": (r["data"] or {}).get("rows", [])[:12]}},
        }
    )
    if not r["success"]:
        raise ValueError(r["error"])
    return r["data"]["rows"]


def cost_breakdown(store, pricing: dict) -> dict:
    calls: list[dict] = []
    ceil = "CAST(duration_min + 0.999999 AS INTEGER)"
    by_type = _sql(
        store,
        (
            "SELECT rideable_type, COUNT(*) AS rides, SUM(" + ceil + ") AS billed_minutes, "
            "SUM(MAX(" + ceil + " - 45, 0)) AS minutes_over_45, ROUND(AVG(duration_min), 2) AS avg_minutes "
            "FROM trips GROUP BY rideable_type ORDER BY rideable_type"
        ),
        calls,
    )
    months = _sql(
        store,
        "SELECT COUNT(DISTINCT ride_month) AS months, MIN(ride_date) AS first_ride, "
        "MAX(ride_date) AS last_ride, COUNT(*) AS rides FROM trips",
        calls,
    )[0]
    weeks = _sql(
        store,
        (
            "SELECT ride_week, COUNT(*) AS rides, ROUND(AVG(duration_min), 1) AS avg_minutes, "
            "SUM(CASE WHEN rideable_type = 'electric_bike' THEN 1 ELSE 0 END) AS ebike_rides, "
            "SUM(CASE WHEN rideable_type = 'electric_bike' THEN " + ceil + " ELSE 0 END) AS ebike_minutes, "
            "SUM(CASE WHEN rideable_type <> 'electric_bike' THEN " + ceil + " ELSE 0 END) AS classic_minutes, "
            "SUM(CASE WHEN rideable_type <> 'electric_bike' THEN MAX("
            + ceil
            + " - 45, 0) ELSE 0 END) AS classic_over_45 "
            "FROM trips GROUP BY ride_week ORDER BY ride_week DESC LIMIT 8"
        ),
        calls,
    )

    ppu, mp = pricing["pay_per_use"], pricing["month_pass"]
    ppu_terms, member_terms = [], []
    for row in by_type:
        t = "electric_bike" if row["rideable_type"] == "electric_bike" else "classic_bike"
        p, m = ppu[t], mp[t]
        billable = row["billed_minutes"] if p["included_min"] == 0 else row["minutes_over_45"]
        ppu_terms.append(f"{row['rides']} * {p['unlock']} + {billable} * {p['per_min']}")
        over = row["minutes_over_45"] if m["included_min"] else row["billed_minutes"]
        member_terms.append(f"{row['rides']} * {m['unlock']} + {over} * {m['per_min']}")
    ppu_total = _calc(" + ".join(f"({x})" for x in ppu_terms) or "0", "USD pay-per-use total", calls)
    residual = _calc(" + ".join(f"({x})" for x in member_terms) or "0", "USD member per-minute/unlock charges", calls)
    fees = _calc(f"{months['months']} * {pricing['month_pass_price']}", "USD month pass fees", calls)
    member_total = _calc(f"{fees} + {residual}", "USD membership total", calls)
    rides_per_month = _calc(f"{months['rides']} / {months['months']}", "rides per month", calls)
    ppu_per_ride = _calc(f"{ppu_total} / {months['rides']}", "USD per ride, pay-per-use", calls)
    member_per_ride = _calc(f"{residual} / {months['rides']}", "USD per ride, member extra charges", calls)
    saving_per_ride = ppu_per_ride - member_per_ride
    break_even = (
        _calc(
            f"{pricing['month_pass_price']} / ({ppu_per_ride} - {member_per_ride})",
            "rides per month to break even",
            calls,
        )
        if saving_per_ride > 0
        else None
    )

    weekly = []
    for w in reversed(weeks):
        spend = _calc(
            f"{w['rides'] - w['ebike_rides']} * {ppu['classic_bike']['unlock']} + {w['classic_minutes']} * "
            f"{ppu['classic_bike']['per_min']} + {w['ebike_rides']} * {ppu['electric_bike']['unlock']} + "
            f"{w['ebike_minutes']} * {ppu['electric_bike']['per_min']}",
            "USD pay-per-use spend",
            calls,
        )
        weekly.append(
            {
                "week": w["ride_week"],
                "rides": w["rides"],
                "avg_minutes": w["avg_minutes"],
                "pay_per_use_spend": round(spend, 2),
            }
        )

    decision = "Buy Monthly Membership" if member_total < ppu_total else "Pay Per Ride/Minute"
    return {
        "decision": decision,
        "pay_per_use_total": round(ppu_total, 2),
        "membership_fees": round(fees, 2),
        "membership_residual_charges": round(residual, 2),
        "membership_total": round(member_total, 2),
        "months": months["months"],
        "rides": months["rides"],
        "first_ride": months["first_ride"],
        "last_ride": months["last_ride"],
        "rides_per_month": round(rides_per_month, 2),
        "break_even_rides_per_month": round(break_even, 2) if break_even else None,
        "by_bike_type": by_type,
        "weekly_last_8": weekly,
        "tool_calls": calls,
    }
