#!/usr/bin/env python3
"""HW7 Part 4: build the two bike-share scenario CSVs from real Bay Wheels trip data.

Source: https://s3.amazonaws.com/baywheels-data/202608-baywheels-tripdata.csv.zip (August 2026),
downloaded to data/bikeshare/downloads/ (gitignored, ~126 MB unzipped).

The public data has no rider id, so each scenario is a set of REAL trips (real ride_id, bike type,
stations, coordinates, time of day and duration) treated as one rider's history. Only the calendar
date is moved, with random.Random(SEED), to spread the trips over the scenario's time window:

  membership_wins   520 trips of 12-55 minutes (classic + electric, as in the data) over 26 weeks
                    -> about 20 rides a week, longer rides
  payperuse_wins    510 classic-bike trips of 3-9 minutes over 48 months
                    -> about 10-11 short rides a month

Writes Homework7/fixtures/bikeshare/scenario_<name>.csv and reports/hw07/raw/bikeshare_trip_summary_<name>.json.

Usage (repo root):  python Homework7/scripts/build_bikeshare_scenarios.py
"""

from __future__ import annotations

import csv
import random
import sys
from datetime import datetime, timedelta

from hw7_common import FIXTURES, RAW, ROOT, banner, write_json

import config

SOURCE = ROOT / "data" / "bikeshare" / "downloads" / "202608-baywheels-tripdata.csv"
SOURCE_URL = "https://s3.amazonaws.com/baywheels-data/202608-baywheels-tripdata.csv.zip"
OUT = FIXTURES / "bikeshare"
FMT = "%Y-%m-%d %H:%M:%S.%f"


def parse(row: dict) -> tuple[datetime, float] | None:
    try:
        start = datetime.strptime(row["started_at"], FMT)
        end = datetime.strptime(row["ended_at"], FMT)
    except (ValueError, KeyError):
        return None
    minutes = (end - start).total_seconds() / 60
    return (start, minutes) if minutes > 0 else None


def build(name: str, rows: list[dict], n: int, slot_start, rng: random.Random) -> list[dict]:
    picked = rng.sample(rows, n)
    out = []
    for i, row in enumerate(picked):
        start, minutes = parse(row)
        day = slot_start(i, n, rng)
        new_start = datetime.combine(day.date(), start.time())
        new_end = new_start + timedelta(minutes=minutes)
        out.append({**row, "started_at": new_start.strftime(FMT)[:-3], "ended_at": new_end.strftime(FMT)[:-3]})
    out.sort(key=lambda r: r["started_at"])
    return out


def summarize(name: str, rows: list[dict], rule: str) -> dict:
    mins = [parse(r)[1] for r in rows]
    starts = [parse(r)[0] for r in rows]
    types = {}
    for r in rows:
        types[r["rideable_type"]] = types.get(r["rideable_type"], 0) + 1
    return {
        "scenario": name,
        "rows": len(rows),
        "selection_rule": rule,
        "source_file": SOURCE.name,
        "source_url": SOURCE_URL,
        "seed": config.SEED,
        "first_ride": min(starts).isoformat(),
        "last_ride": max(starts).isoformat(),
        "rideable_types": types,
        "duration_min": {
            "mean": round(sum(mins) / len(mins), 2),
            "min": round(min(mins), 2),
            "max": round(max(mins), 2),
        },
        "missing_end_station": sum(1 for r in rows if not r["end_station_name"]),
        "note": "Real trip rows; only the calendar date was moved to model one rider's history.",
    }


def main() -> int:
    banner("Part 4 build bike-share scenarios from real Bay Wheels trips")
    if not SOURCE.exists():
        print(f"Missing {SOURCE}. Download and unzip {SOURCE_URL} into {SOURCE.parent}.")
        return 1
    with SOURCE.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        all_rows = [r for r in reader if parse(r)]
    print(f"read {len(all_rows):,} valid trips from {SOURCE.name}")
    rng = random.Random(config.SEED)

    long_rides = [r for r in all_rows if 12 <= parse(r)[1] <= 55]
    short_classic = [r for r in all_rows if r["rideable_type"] == "classic_bike" and 3 <= parse(r)[1] <= 9]
    print(f"candidates: {len(long_rides):,} rides of 12-55 min, {len(short_classic):,} classic rides of 3-9 min")

    week0 = datetime(2026, 3, 2)  # Monday; 26 weeks -> 2026-03-02 .. 2026-08-30

    def weekly(i: int, n: int, r: random.Random) -> datetime:
        return week0 + timedelta(weeks=i * 26 // n, days=r.randrange(7))

    month0 = datetime(2022, 9, 1)

    def monthly(i: int, n: int, r: random.Random) -> datetime:
        m = i * 48 // n
        first = datetime(month0.year + (month0.month - 1 + m) // 12, (month0.month - 1 + m) % 12 + 1, 1)
        return first + timedelta(days=r.randrange(28))

    OUT.mkdir(parents=True, exist_ok=True)
    scenarios = {
        "membership_wins": (
            build("membership_wins", long_rides, 520, weekly, rng),
            "520 random real trips of 12-55 minutes, spread over 26 weeks (2026-03-02 to 2026-08-30)",
        ),
        "payperuse_wins": (
            build("payperuse_wins", short_classic, 510, monthly, rng),
            "510 random real classic-bike trips of 3-9 minutes, spread over 48 months (2022-09 to 2026-08)",
        ),
    }
    for name, (rows, rule) in scenarios.items():
        path = OUT / f"scenario_{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        summary = summarize(name, rows, rule)
        write_json(RAW / f"bikeshare_trip_summary_{name}.json", summary)
        print(
            f"\n{path.relative_to(ROOT)}: {summary['rows']} rows, {summary['first_ride'][:10]} to "
            f"{summary['last_ride'][:10]}, mean {summary['duration_min']['mean']} min, "
            f"types {summary['rideable_types']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
