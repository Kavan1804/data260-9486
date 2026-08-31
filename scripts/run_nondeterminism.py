import argparse
import csv
import json
import math
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE_FILE = ROOT / "reports/hw01/cases/nondeterminism_input.json"
RAW_DIR = ROOT / "reports/hw01/raw"
RUNS_FILE = RAW_DIR / "nondeterminism_runs.json"
CSV_FILE = RAW_DIR / "nondeterminism_runs.csv"
METRICS_FILE = RAW_DIR / "nondeterminism_metrics.json"


def percentile(values, percent):
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return ordered[lower]

    return ordered[lower] + (
        ordered[upper] - ordered[lower]
    ) * (position - lower)


def save_results(results):
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    RUNS_FILE.write_text(
        json.dumps(results, indent=2),
        encoding="utf-8",
    )

    with CSV_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "temperature",
                "run",
                "timestamp",
                "latency_ms",
                "tags",
                "summary",
            ],
        )
        writer.writeheader()

        for result in results:
            row = dict(result)
            row["tags"] = json.dumps(row["tags"])
            writer.writerow(row)


def extract_package(output):
    marker = " Publish Package "
    position = output.rfind(marker)

    if position == -1:
        raise ValueError("Publish Package was not found in agent output")

    payload = output[position + len(marker):].strip()
    return json.loads(payload)


def calculate_metrics(results, expected_runs):
    metrics = {}

    for temperature in (0.0, 0.7):
        selected = [
            result for result in results
            if result["temperature"] == temperature
            and result["run"] <= expected_runs
        ]

        tag_sets = {
            tuple(sorted(result["tags"]))
            for result in selected
        }

        tag_counts = Counter(
            tag
            for result in selected
            for tag in set(result["tags"])
        )

        latencies = [result["latency_ms"] for result in selected]

        metrics[str(temperature)] = {
            "runs": len(selected),
            "distinct_tag_sets": len(tag_sets),
            "tags_in_all_runs": sorted(
                tag for tag, count in tag_counts.items()
                if count == expected_runs
            ),
            "tags_in_exactly_one_run": sorted(
                tag for tag, count in tag_counts.items()
                if count == 1
            ),
            "latency_ms": {
                "p50": round(percentile(latencies, 50), 2),
                "p95": round(percentile(latencies, 95), 2),
                "p99": round(percentile(latencies, 99), 2),
            },
        }

    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-per-temperature", type=int, default=20)
    parser.add_argument("--model", default="qwen3:4b")
    args = parser.parse_args()

    case = json.loads(CASE_FILE.read_text(encoding="utf-8"))
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if RUNS_FILE.exists():
        results = json.loads(RUNS_FILE.read_text(encoding="utf-8"))
    else:
        results = []

    completed = {
        (result["temperature"], result["run"])
        for result in results
    }

    for temperature in (0.0, 0.7):
        for run_number in range(1, args.runs_per_temperature + 1):
            key = (temperature, run_number)

            if key in completed:
                print(f"Skipping completed run: temperature={temperature}, run={run_number}")
                continue

            command = [
                sys.executable,
                str(ROOT / "agents_demo.py"),
                "--title", case["title"],
                "--content", case["content"],
                "--email", case["email"],
                "--model", args.model,
                "--temperature", str(temperature),
                "--strict",
            ]

            print(f"Running temperature={temperature}, run={run_number}")

            started = time.perf_counter()
            process = subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 2)

            if process.returncode != 0:
                print(process.stderr, file=sys.stderr)
                raise RuntimeError(
                    f"Run failed: temperature={temperature}, run={run_number}"
                )

            package = extract_package(process.stdout)
            final = package["agents"]["final"]

            results.append({
                "temperature": temperature,
                "run": run_number,
                "timestamp": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "latency_ms": latency_ms,
                "tags": final["tags"],
                "summary": final["summary"],
            })

            save_results(results)
            print(f"Completed in {latency_ms:.2f} ms: {final['tags']}")

    metrics = calculate_metrics(results, args.runs_per_temperature)
    METRICS_FILE.write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()