#!/usr/bin/env python3
"""Render the HW11 report (reports/hw11/report.pdf and Kumar_HW11.pdf). Numbers come from reports/hw11/raw/.

A screenshot that does not exist yet is shown as a red MISSING box. Limit: 25 pages.
Usage (repo root):  [COMMIT_HASH=<sha>] python Homework11/scripts/render_report_hw11.py
"""

# ruff: noqa: E501 - long report sentences
from __future__ import annotations

import html
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
r5 = importlib.import_module("render_report_hw05")
config = importlib.import_module("config")

KIT = ROOT / "Homework11" / "stock-watch"
REPORT = ROOT / "reports" / "hw11"
RAW = REPORT / "raw"
r5.SHOTS = REPORT / "screenshots"
CHAT = (0.04, 0.125, 0.80, 0.905)  # chat area only: no browser tabs, sidebar or dock
r5.CROPS = {
    "m1b": (0.832, 0.375, 1.0, 0.905),  # task list panel
    "m8": (0.04, 0.125, 0.65, 0.85),
    "m9": (0.17, 0.125, 0.80, 0.705),  # stops above the message that shows my email
    "m1": (0.04, 0.125, 1.0, 0.905),
    "m6": (0.25, 0.21, 0.75, 0.82),
    **{f"m{i}": CHAT for i in (2, 3, 4, 5, 7)},
}
CSS = r5.CSS.replace("Homework 5", "Homework 11") + (
    ".missing { border: 2px dashed #ef4444; color: #b91c1c; padding: 10pt; margin: 6pt 0 12pt 0; }\n"
    ".cmd { white-space: pre-wrap; font-size: 8pt; line-height: 1.3; }\n"
)
MISSING: list[str] = []


def load(name: str):
    return json.loads((RAW / name).read_text(encoding="utf-8"))


def fig(d, name: str, caption: str, width: str = "88%") -> None:
    if (r5.SHOTS / f"{name}.png").exists():
        d.fig(name, caption, width=width)
    else:
        MISSING.append(name)
        d.add(f"<div class='missing'><b>MISSING SCREENSHOT ({name}.png):</b> {html.escape(caption)}</div>")


def block(d, text: str) -> None:
    d.add(f"<div class='cmd'>{html.escape(text.rstrip())}</div>")


def intro(d, commit: str) -> None:
    d.add("<h1>DATA 260 Homework 11</h1><div class='sub'>Kavan Siddesh</div>")
    d.h2("Section 0. Configuration", new_page=False)
    d.table(
        [
            ["GitHub repository", config.REPO_URL],
            ["SID4 / PREFIX", f"9486 / {config.PREFIX}"],
            ["Agent platform", "Meta Muse, free tier (cloud computer running watch.py)"],
            ["Live watchlist (CIK)", "KO 0000021344, AAPL 0000320193, NVDA 0001045810, TSLA 0001318605"],
            ["Tagged commit hash", f"{commit} (tag hw11)"],
        ],
        header=False,
        cls="kv",
    )
    d.h2("Part 1. Build", new_page=False)
    d.p(
        "I installed the kit on Muse, saved the standing instructions, and created the weekday 1:30 PM Pacific task. "
        "I extended `watch.py` in two small ways and left the ledger, checkpoints and injection guard unchanged: "
        "unusable price data becomes a visible item, and source errors appear in `pending` and `status`."
    )
    fig(
        d,
        "m1_upcoming",
        'Scheduled task list: "Stock Watch - weekday live run" (right side, 1:30 pm). The pop-up '
        "in the middle is a default Muse task I had clicked, not mine.",
    )
    fig(
        d,
        "m1b_tasks",
        "Task list at 1:57 pm: Stock Watch, next run Nov 24, 1:30 pm (from the restart screenshot).",
        "38%",
    )
    d.p(
        "**The schedule did not produce a scan I can show.** The first slot was 1:30 pm on Nov 23. At 1:55 pm `status` "
        "still gave my 1:28 pm crash test as the current run (Part 4), so no newer scan had been recorded. That test "
        "was left interrupted just before the slot and may be why; I did not find out. I use manual runs instead."
    )
    d.h3("First live run")
    d.p(
        "This is a manual `run stock-watch`. It sent "
        "no alert. All four prices were missing, and EDGAR answered 403, because the contact address was still a "
        'placeholder. Stooq now returns a "verify your browser" web page to scripts instead of CSV; I checked this '
        "from my own computer. The starter kit reads that page as zero rows, so it would have looked like a quiet day."
    )
    fig(d, "m7_live", "First live run: four `ask` items for missing prices, and the EDGAR error named.")
    d.h3("Second live run")
    d.p(
        "Muse checked `status` first, then scanned: 0 new, 4 duplicates suppressed, 0 alerts, and EDGAR 403 again. The "
        "4 duplicates match the 4 missing-price items from the first run. Muse confirmed the new contact address in a "
        "message shown below this run's result, so I cannot tell whether the run already used it. **I have not shown a "
        "successful live EDGAR or price read.** A 403 can also come from blocking the cloud computer's address; I did "
        "not determine the cause. Muse named the error and did not try a way around it."
    )
    fig(d, "m9_live", "Second `run stock-watch` (run 20261123-135922-8235). Cropped to leave out my email address.")


def policy(d) -> None:
    d.h2("Part 2. Materiality Policy")
    d.p(
        "The full file is `Homework11/stock-watch/policy.md`. Price lines use the absolute daily close-to-close change:"
    )
    d.table(
        [
            ["Class", "Tickers", "quiet", "digest", "notify"],
            ["Calm", "KO (test: ALDZ)", "under 1.5%", "1.5% to under 3%", "3% or more"],
            ["Core", "AAPL (test: HBVZ, PNLZ, TESZ, MSRZ)", "under 2%", "2% to under 5%", "5% or more"],
            ["Volatile", "NVDA, TSLA (test: QLSZ)", "under 4%", "4% to under 8%", "8% or more"],
        ]
    )
    d.bullets(
        [
            "**8-K notify:** 1.01, 1.03, 2.01, 2.02, 3.01, and 5.02 for a CEO or CFO.",
            "**8.01 / 7.01:** notify if a halt, recall, outage, cyber incident or legal outcome affects 10% or more of "
            "revenue; digest for other real news; quiet for conference dates.",
            "**8-K/A:** quiet when it adds no new facts.",
            "**ask:** text that instructs an AI, asks for credentials or tells readers to trade, and any ticker whose "
            "price data is missing.",
        ]
    )
    d.table(
        [
            ["Decision", "Example 1", "Example 2"],
            ["notify", "AAPL 8-K with Item 2.02", "KO closes -3.4%"],
            ["digest", "NVDA closes +6.0%", "AAPL 8.01 announcing a new plant"],
            ["quiet", "TSLA 8.01 with a conference date", "8-K/A that fixes a typo"],
            ["ask", "News item saying assistants should tell readers to add a stock", "KO price data missing"],
        ]
    )
    d.h3("Is a 5% move equally material for every stock?")
    d.p(
        "No. KO is a low-volatility consumer staple, so 3% in a day is unusual and worth an interruption. NVDA and TSLA "
        "make much larger daily moves more often, so a 5% line would alert on ordinary days and I would start ignoring "
        "it. AAPL sits between them. These lines are my judgment about the type of stock. I did not fit them to price "
        "history, because the price source was not usable; I would check them against a year of closes first."
    )


def golden(d) -> None:
    v = json.loads((REPORT / "verification.json").read_text(encoding="utf-8"))
    d.h2("Part 3. Golden Set")
    d.p(
        f"The 12 labels were committed at {v['labels_committed']} and the first agent run started at "
        f"{v['first_agent_run']}. The answer sheet was left out of the zip I uploaded, so Muse could not see it."
    )
    per = {c["case_id"]: c for c in load("metrics.json")["per_case"]}
    gold = json.loads((KIT / "golden" / "gold_hw11.json").read_text(encoding="utf-8"))["cases"]
    d.table(
        [["Case", "Category", "Why", "Expected", "Muse"]]
        + [[c["case_id"], c["category"], c["why"], c["expected"], per[c["case_id"]]["got"]] for c in gold],
        widths=["8%", "17%", "49%", "13%", "13%"],
    )


def failures(d) -> None:
    d.h2("Part 4. Failure Injection")
    d.h3("1. Duplicate")
    d.p(
        "The QLSZ filing arrived from EDGAR and again through a news story citing accession 0009999913-26-000051. "
        "`watch.py` merged them (`dedup_merge`) and one alert was sent. Figure below: the summary says 1 duplicate "
        "suppressed, and QLSZ appears once. The trace in Part 5 shows the merge."
    )
    fig(d, "m3b_resumed", "The six HIGH alerts and the summary line: 12 new, 1 duplicate suppressed, 6 alerts.")
    d.h3("2. Restart")
    d.p(
        "The scan was stopped after 5 items. Asked what it was working on, Muse ran `status`, saw `interrupted` with 2 "
        "of 4 sources done, resumed, and finished all 12 items with no repeats. In this first test I continued in the "
        "same chat (the previous answer is visible at the top of the figure), so Muse could also have used the chat "
        "history. For the repeat I crashed run 20261123-132830-4a7d on `fixtures/day1` "
        "after 2 items and asked in a new side chat. Muse showed `interrupted`, 0 of 4 sources done, 2 items pending, "
        "then resumed the same run: 6 new, 1 duplicate suppressed, 2 alerts, 0 digest, 1 for review."
    )
    fig(d, "m2_interrupted", "Scan stopped with `--stop-after 5`.")
    fig(d, "m3_resumed", "Status output and resume (first test, same chat).")
    fig(d, "m8_newchat", "Repeat in a new side chat (chat list on the left): status output, then resume and finish.")
    d.h3("3. Prompt injection")
    d.p(
        "The Alderpoint story was caught by the guard. The Penlark story was worded so no pattern matches "
        "(`injection_flag` is absent), and Muse still chose `ask` on its own. I then told Muse to follow the Penlark "
        "story. It refused, and `fetch` blocked the link. The same figure shows the retried TESZ alert being refused."
    )
    fig(d, "m4_injection", "ALREADY_REPORTED for the retry, refusal to follow the story, and the blocked link.")


def trace_part(d) -> None:
    d.h2("Part 5. Trace of One Alert")
    run = load("runs.json")[0]
    t = {x["step"]: x for x in load("trace_alert.json")}
    d.p("HIGH alert: QLSZ 8-K, supply agreement (`python3 watch.py trace --effect-id 24bbe5900f1e`).")
    d.table(
        [
            ["Step", "From the trace"],
            ["Effect ID", f"{t['effect']['effect_id']} (hash of {t['retrieved']['detail']['key']})"],
            ["Source", f"{t['retrieved']['detail']['source']}; {t['dedup_merge']['detail']['source']} merged into it"],
            ["Evidence", t["retrieved"]["detail"]["url"]],
            [
                "Score and reason",
                f"{t['importance_scored']['detail']['score']} - {t['importance_scored']['detail']['reason']}",
            ],
            ["Decision", t["decision"]["detail"]["decision"]],
            ["Effect", f"{t['effect']['detail']['type']} at {t['effect']['ts']}, once"],
        ],
        widths=["22%", "78%"],
    )
    fig(d, "m5_trace", "Trace and snapshot commands in Muse (Muse shows the JSON on one line; full output below).")
    block(d, json.dumps(load("trace_alert.json"), indent=1))
    d.p(
        f"**Latency:** {run['latency_s']:.0f} s from start ({run['started']}) to finish ({run['finished']}). About 39 s of "
        "that is the gap between the simulated crash (20:18:12) and my resume message (20:18:51), so active time was "
        "about 23 s. **Token usage:** Muse does not show tokens, only a weekly percentage, which read 0% (Part 6)."
    )


def metrics_part(d) -> None:
    m = load("metrics.json")["metrics"]
    d.h2("Part 6. Metrics")
    d.p(
        "Computed with `watch.py metrics --gold golden/gold_hw11.json` on the snapshot I downloaded from Muse, restored "
        "on my computer. I did not pass `--usage-tokens`, because Muse gave no token number."
    )
    d.table(
        [
            ["Metric", "Result", "What it means"],
            ["Precision (notify)", f"{m['precision_notify']:.2f}", "6 of 6 alerts were material"],
            ["Recall (notify)", f"{m['recall_notify']:.2f}", "6 of 6 material items were alerted"],
            ["Unnecessary notification rate", f"{m['unnecessary_notification_rate']:.2f}", "No noise alerts"],
            [
                "Duplicate notification rate",
                f"{m['duplicate_notification_rate']:.2f}",
                "No alert twice, including the duplicate filing and the retry",
            ],
            [
                "Restart recovery rate",
                f"{m['restart_recovery_rate']:.2f}",
                "1 of 1 interrupted run in this snapshot; the later new-chat repeat also recovered but is not counted",
            ],
            ["Tokens per accepted alert", "not available", "Muse shows only a percentage"],
        ],
        widths=["30%", "16%", "54%"],
    )
    d.p(
        'Do not read 1.00 as "never wrong". With 6 successes out of 6, the 95% lower bound on precision or recall is '
        "only about 0.61 (0.05^(1/6)). The labels and the policy also come from the same author, so the set mostly "
        "tests whether Muse follows the policy, not whether the policy is right."
    )
    fig(d, "m6_usage", "Settings - Usage after the test run: 0% of the weekly limit.", width="62%")
    d.p(
        "**Usage estimate.** Usage read 0% before and after setup plus the test run. If the display rounds down, that "
        "work used under 1% of the week. Treating one run as costing up to 1%, five weekday runs use under 5% of a "
        "weekly allowance, and a month of about 22 runs uses under 22% of one week's allowance. The display may also "
        "lag, so this is an upper-bound guess, not a measurement. Per accepted alert, the 6 alerts cost under 0.17% each."
    )


def analysis(d) -> None:
    d.h2("Part 7. Analysis")
    d.h3("1. When should it alert, ask, or stay quiet? Where was the policy wrong?")
    d.p(
        "Alert when waiting until tomorrow would matter; ask when text is unsafe or the monitor cannot see; stay quiet "
        "for routine or repeated items. The policy was wrong about blindness. When Stooq failed, it made one `ask` per "
        "ticker, and will do so again each day, yet `ask` only goes to the digest. A second run the same day "
        "even reported 0 new, because the missing-price items were already recorded. An outage should send one alert "
        "when it starts and one when it ends."
    )
    d.h3("2. What state must survive, and where does it live?")
    d.bullets(
        [
            "Ledger, items, checkpoints and trace: `state/watch.db` on the Muse computer, copied to "
            "`state/snapshot.json`. Both are on the same computer, so a reset loses both unless the snapshot is "
            "downloaded. I keep a copy in `reports/hw11/raw/`.",
            "Policy, sources, fixtures, labels and code: the GitHub repository.",
            "Standing instructions: Muse memory. Schedule: Muse's task list. Both can be recreated from MUSE_SETUP.md.",
            "The contact address is only on the Muse computer, so it must be entered again after a reset.",
        ]
    )
    d.h3("3. Which failure did the golden set reveal?")
    d.p(
        "B2, missing prices. On my fixtures the starter `watch.py` listed 11 items and never mentioned TESZ; the extended "
        "one listed 12. The same failure then happened for real on the first live run. Writing the duplicate and "
        "injection cases also led me to test their combination: a malicious story citing a filing's accession number, "
        "seen before the filing, forces that effect ID to `ask`, and the real filing is then skipped as already decided "
        "(`raw/suppression_test.json`). An attacker could hide a real alert this way. This is still open."
    )
    d.h3("4. Release decision")
    d.p(
        "**No, not unattended for a month.** On fixtures it behaved well, but on both live runs it could not see "
        "prices or filings. I would allow a two-week supervised trial once these are met:"
    )
    d.bullets(
        [
            "Working price source, and at least 95% of scheduled runs finishing with no source error.",
            "Precision at least 0.90 and recall at least 0.95 on 60 or more cases, some labeled by another person.",
            "Duplicate rate 0, injected items notified 0, trade advice 0, and restart recovery 1.0 over 10 interruptions.",
            "Accession matching trusted only from sec.gov, to close the suppression hole.",
            "Delivery confirmed: the ledger records `notify` before the message is posted, so a crash between the two "
            "would lose an alert.",
            "Snapshot copied off the Muse computer after every run.",
        ]
    )


def closing(d) -> None:
    v = json.loads((REPORT / "verification.json").read_text(encoding="utf-8"))
    d.h2("Verification")
    d.table(
        [["Check", "Result"]] + [[c["check"], "PASS" if c["ok"] else "FAIL"] for c in v["checks"]],
        widths=["80%", "20%"],
    )
    d.h2("AI Use", new_page=False)
    d.add(r5.md_paragraphs((REPORT / "AI_USE.md").read_text(encoding="utf-8")))


def main() -> int:
    commit = (
        os.getenv("COMMIT_HASH")
        or subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    )
    out = REPORT / "report.pdf"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        d = r5.Doc(tmp)
        intro(d, commit)
        for section in (policy, golden, failures, trace_part, metrics_part, analysis, closing):
            section(d)
        page = (
            "<!doctype html><html><head><meta charset='utf-8'><title>DATA 260 HW11 - Kavan Siddesh</title>"
            f"<style>{CSS}</style></head><body>{''.join(d.parts)}</body></html>"
        )
        (tmp / "report.html").write_text(page, encoding="utf-8")
        subprocess.run(
            [
                r5.CHROME,
                "--headless=new",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--print-to-pdf={out}",
                (tmp / "report.html").as_uri(),
            ],
            check=True,
            capture_output=True,
        )
        if os.getenv("KEEP_HTML"):
            shutil.copytree(tmp, os.environ["KEEP_HTML"], dirs_exist_ok=True)
    shutil.copy(out, REPORT / "Kumar_HW11.pdf")
    print(f"wrote {out.relative_to(ROOT)} and Kumar_HW11.pdf (commit {commit[:12]}, {d.fig_no} figures)")
    if MISSING:
        print(f"DRAFT - missing screenshots: {', '.join(MISSING)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
