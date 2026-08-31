#!/usr/bin/env python3
"""Render the Homework 1 report to PDF using Pillow."""

from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from matplotlib import font_manager


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "hw01"
SCREENSHOT_DIR = REPORT_DIR / "screenshots"
OUTPUT_PDF = REPORT_DIR / "report.pdf"
TEMP_DIR = Path("/private/tmp/hw1-report-pages")

W, H = 1600, 2070
MARGIN = 70
BODY_W = W - 2 * MARGIN


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = font_manager.findfont(name, fallback_to_default=True)
    return ImageFont.truetype(path, size=size)


TITLE = font("DejaVu Sans", 34)
H1 = font("DejaVu Sans", 24)
H2 = font("DejaVu Sans", 18)
BODY = font("DejaVu Sans", 15)
SMALL = font("DejaVu Sans", 13)
MONO = font("DejaVu Sans Mono", 13)


def new_page() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (W, H), "white")
    return image, ImageDraw.Draw(image)


def line_height(fnt: ImageFont.FreeTypeFont, extra: int = 6) -> int:
    bbox = fnt.getbbox("Ag")
    return (bbox[3] - bbox[1]) + extra


def draw_wrapped(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, width: int, fnt: ImageFont.FreeTypeFont, fill="black", spacing: int = 6):
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        words = paragraph.split()
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if draw.textlength(candidate, font=fnt) <= width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    h = line_height(fnt, spacing)
    for line in lines:
        draw.text((x, y), line, font=fnt, fill=fill)
        y += h
    return y


def draw_bullets(draw: ImageDraw.ImageDraw, bullets: list[str], x: int, y: int, width: int, fnt: ImageFont.FreeTypeFont = BODY):
    bullet_indent = 26
    for bullet in bullets:
        wrapped = textwrap.wrap(bullet, width=92)
        draw.text((x, y), "-", font=fnt, fill="black")
        draw_wrapped(draw, wrapped[0], x + bullet_indent, y, width - bullet_indent, fnt)
        y += line_height(fnt)
        for extra in wrapped[1:]:
            draw_wrapped(draw, extra, x + bullet_indent, y, width - bullet_indent, fnt)
            y += line_height(fnt)
        y += 5
    return y


def draw_table(draw: ImageDraw.ImageDraw, rows: list[list[str]], x: int, y: int, col_widths: list[int], fnt: ImageFont.FreeTypeFont = SMALL, row_pad: int = 10):
    heights = []
    wrapped_rows = []
    for row in rows:
        wrapped = []
        row_h = 0
        for cell, width in zip(row, col_widths):
            cell_lines = textwrap.wrap(cell, width=max(8, int(width / 8.5)))
            if not cell_lines:
                cell_lines = [""]
            wrapped.append(cell_lines)
            row_h = max(row_h, len(cell_lines) * line_height(fnt, 3))
        wrapped_rows.append(wrapped)
        heights.append(row_h + row_pad * 2)

    cur_y = y
    for row, wrapped, row_h in zip(rows, wrapped_rows, heights):
        cur_x = x
        draw.rectangle([x, cur_y, x + sum(col_widths), cur_y + row_h], outline="#cbd5e1", width=2)
        cell_x = x
        for idx, (cell, lines, width) in enumerate(zip(row, wrapped, col_widths)):
            if idx > 0:
                draw.line([cell_x, cur_y, cell_x, cur_y + row_h], fill="#cbd5e1", width=2)
            text_y = cur_y + row_pad
            for line in lines:
                draw.text((cell_x + 10, text_y), line, font=fnt, fill="black")
                text_y += line_height(fnt, 3)
            cell_x += width
        cur_y += row_h
    return cur_y


def add_image(draw: ImageDraw.ImageDraw, path: Path, box: tuple[int, int, int, int], caption: str, caption_font: ImageFont.FreeTypeFont = SMALL):
    left, top, right, bottom = box
    draw.rectangle(box, outline="#d1d5db", width=2)
    img = Image.open(path).convert("RGB")
    max_w = right - left - 10
    max_h = bottom - top - 34
    img.thumbnail((max_w, max_h))
    px = left + (max_w - img.width) // 2 + 5
    py = top + 5
    draw.bitmap((px, py), img)
    # The bitmap paste above only works for RGB images with the current Pillow version.


def paste_fit(page: Image.Image, path: Path, box: tuple[int, int, int, int]):
    left, top, right, bottom = box
    img = Image.open(path).convert("RGB")
    max_w = right - left
    max_h = bottom - top
    img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    px = left + (max_w - img.width) // 2
    py = top + (max_h - img.height) // 2
    page.paste(img, (px, py))


def caption(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, width: int, fnt: ImageFont.FreeTypeFont = SMALL):
    return draw_wrapped(draw, text, x, y, width, fnt)


def build_pages() -> list[Image.Image]:
    pages: list[Image.Image] = []

    # Page 1: configuration
    page, draw = new_page()
    y = MARGIN
    draw.text((MARGIN, y), "DATA 260 Homework 1", font=TITLE, fill="black")
    y += 60
    draw.text((MARGIN, y), "Section 0. Personal Configuration and Domain", font=H1, fill="black")
    y += 40
    rows = [
        ["SID4", "9486"],
        ["PORT_BASE", "8486"],
        ["PREFIX", "s9486"],
        ["SEED", "9486"],
        ["VERIFY_SEED", "269486"],
        ["DOMAIN_ID", "6"],
        ["Assigned Domain", "Rental housing listings"],
        ["Hardware", "Apple Mac with M1 chip and 8 GB unified memory"],
        ["Local Model", "qwen3:4b"],
        ["Content-complete source commit hash", "832703b"],
        ["Final submission tag", "hw1"],
    ]
    y = draw_table(draw, rows, MARGIN, y, [430, 850], fnt=SMALL)
    y += 24
    y = draw_wrapped(draw, "The recommended qwen3:8b model was replaced with qwen3:4b because the available Mac hardware has only 8 GB of unified memory, so the smaller model is more practical for repeated local runs.", MARGIN, y, BODY_W, BODY)
    y += 18
    y = draw_wrapped(draw, "Repository notes: the shared adapter lives in src/model_client.py, the strict review prompt is in AGENT.md, and the final PDF is generated from the same evidence stored in reports/hw01/.", MARGIN, y, BODY_W, BODY)
    y += 14
    draw.text((MARGIN, y), "Reproducible commands", font=H2, fill="black")
    y += 28
    y = draw_wrapped(draw, "python3 -m http.server 8486 --directory app", MARGIN, y, BODY_W, MONO)
    y = draw_wrapped(draw, "docker build -t data260-hw1:s9486 .", MARGIN, y, BODY_W, MONO)
    y = draw_wrapped(draw, "docker run --name data260-hw1-s9486 -p 8486:80 data260-hw1:s9486", MARGIN, y, BODY_W, MONO)
    y = draw_wrapped(draw, "docker stop data260-hw1-s9486", MARGIN, y, BODY_W, MONO)
    y = draw_wrapped(draw, "docker rm data260-hw1-s9486", MARGIN, y, BODY_W, MONO)
    pages.append(page)

    # Page 2: Part 1 screenshots
    page, draw = new_page()
    y = MARGIN
    draw.text((MARGIN, y), "Section 1. Part 1: Rental Listing Application", font=H1, fill="black")
    y += 34
    bullets = [
        "The HTML form collects the domain fields from DOMAIN_SCHEMA.md.",
        "The JavaScript validates the description length and terms checkbox, serializes the listing, logs the important fields, and adds a submissionDate timestamp.",
    ]
    y = draw_bullets(draw, bullets, MARGIN, y, BODY_W)
    y += 6
    cols = 2
    box_w = (BODY_W - 28) // 2
    box_h = 420
    items = [
        ("part1_localhost_app.png", "Local app in the browser"),
        ("part1_invalid_description_alert.png", "Invalid description submission"),
        ("part1_missing_terms_alert.png", "Missing terms submission"),
        ("part1_docker_localhost.png", "Docker-backed localhost app"),
        ("part1_docker_container.png", "Docker container evidence"),
        ("part1_ecs_public_ip.png", "ECS public IP evidence"),
    ]
    for idx, (name, cap) in enumerate(items):
        row = idx // 2
        col = idx % 2
        left = MARGIN + col * (box_w + 28)
        top = y + row * (box_h + 56)
        paste_fit(page, SCREENSHOT_DIR / name, (left, top, left + box_w, top + box_h))
        caption(draw, cap, left, top + box_h + 6, box_w, SMALL)
    y += 2 * (box_h + 56)
    pages.append(page)

    # Page 3: Part 2
    page, draw = new_page()
    y = MARGIN
    draw.text((MARGIN, y), "Section 2. Part 2: Multi-Agent Rental-Domain Demo", font=H1, fill="black")
    y += 34
    draw.text((MARGIN, y), "Exact command", font=H2, fill="black")
    y += 28
    command = (
        'python3 agents_demo.py --title "Two-Bedroom Apartment Near SJSU" '
        '--content "A furnished two-bedroom apartment with in-unit laundry, secure parking, '
        'and convenient access to public transit is available near the San Jose State University campus." '
        '--email "kavan.siddeshkumar@sjsu.edu" --model qwen3:4b --strict | tee reports/hw01/raw/agent_demo_part2.txt'
    )
    y = draw_wrapped(draw, command, MARGIN, y, BODY_W, MONO)
    y += 8
    left = MARGIN
    top = y
    box_w = (BODY_W - 24) // 2
    box_h = 470
    paste_fit(page, SCREENSHOT_DIR / "part2_planner_reviewer.png", (left, top, left + box_w, top + box_h))
    caption(draw, "Planner and Reviewer", left, top + box_h + 6, box_w, SMALL)
    paste_fit(page, SCREENSHOT_DIR / "part2_finalized_output.png", (left + box_w + 24, top, left + 2 * box_w + 24, top + box_h))
    caption(draw, "Finalized Output and Publish Package", left + box_w + 24, top + box_h + 6, box_w, SMALL)
    y = top + box_h + 40
    answers = [
        "Q1: The finalized tags were two-bedroom apartment near sjsu, furnished two-bedroom, and secure parking.",
        "Q2: The final summary was: Furnished two-bedroom apartment near SJSU offers in-unit laundry and secure parking with public transit access.",
        "Q3: No issues remained in the final output; data.issues was an empty array.",
    ]
    y = draw_bullets(draw, answers, MARGIN, y, BODY_W, BODY)
    pages.append(page)

    # Page 4: Part 3
    page, draw = new_page()
    y = MARGIN
    draw.text((MARGIN, y), "Section 3. Part 3: Non-Determinism Measurement", font=H1, fill="black")
    y += 34
    y = draw_wrapped(draw, "The fixed experiment input is preserved in reports/hw01/cases/nondeterminism_input.json and was not regenerated.", MARGIN, y, BODY_W, BODY)
    y += 10
    rows = [
        ["Metric", "Temperature 0.0", "Temperature 0.7"],
        ["Runs", "20", "20"],
        ["Distinct tag sets", "1", "3"],
        ["Tags in all runs", "furnished two-bedroom, secure parking, two-bedroom apartment near sjsu", "furnished two-bedroom"],
        ["Tags in exactly one run", "None", "convenient access"],
        ["p50 latency", "74523.73 ms", "80115.68 ms"],
        ["p95 latency", "103968.01 ms", "91286.90 ms"],
        ["p99 latency", "120482.96 ms", "96006.23 ms"],
    ]
    y = draw_table(draw, rows, MARGIN, y, [280, 620, 620], fnt=SMALL)
    y += 18
    paste_fit(page, SCREENSHOT_DIR / "part3_metrics.png", (MARGIN, y, W - MARGIN, y + 760))
    caption(draw, "Non-determinism metrics and run output", MARGIN, y + 768, BODY_W, SMALL)
    pages.append(page)

    # Page 5: Part 4, page 1
    page, draw = new_page()
    y = MARGIN
    draw.text((MARGIN, y), "Section 4. Part 4: Strict Code Review Client", font=H1, fill="black")
    y += 34
    y = draw_wrapped(draw, "hw1_client.py loads AGENT.md as the system prompt and sends every request through src/model_client.ModelClient.complete(messages, tools=None). The adapter centralizes the Ollama call, token accounting, and optional tool support.", MARGIN, y, BODY_W, BODY)
    y += 14
    y = draw_wrapped(draw, "AGENT.md requires bullet-point-only code review responses.", MARGIN, y, BODY_W, BODY)
    y += 12
    rows = [
        ["Turn", "Input tokens", "Output tokens", "Total tokens"],
        ["1", "125", "256", "381"],
        ["2", "407", "256", "663"],
        ["3", "699", "256", "955"],
        ["4", "986", "256", "1242"],
        ["5", "1272", "256", "1528"],
    ]
    y = draw_table(draw, rows, MARGIN, y, [160, 240, 240, 240], fnt=SMALL)
    y += 16
    rows2 = [
        ["Snapshot", "Turn count", "Cumulative input", "Cumulative output", "Cumulative total", "Serialized history length"],
        ["After turn 3", "3", "1231", "768", "1999", "4449 characters"],
        ["After turn 5", "5", "3489", "1280", "4769", "7102 characters"],
    ]
    y = draw_table(draw, rows2, MARGIN, y, [220, 120, 180, 180, 160, 220], fnt=SMALL)
    y += 14
    y = draw_wrapped(draw, "The client prints Bullet-only format check after each response. The evidence shows FAIL because the model returned numbered lists instead of pure bullet points, which confirms the checker is working and the transcript captured the non-compliant output honestly.", MARGIN, y, BODY_W, BODY)
    pages.append(page)

    # Page 6: Part 4 screenshots and closing
    page, draw = new_page()
    y = MARGIN
    draw.text((MARGIN, y), "Section 4. Part 4 Evidence and Closing Notes", font=H1, fill="black")
    y += 34
    left = MARGIN
    top = y
    box_w = (BODY_W - 24) // 2
    box_h = 700
    paste_fit(page, SCREENSHOT_DIR / "part4_stats_turn3.png", (left, top, left + box_w, top + box_h))
    caption(draw, "Turn 3 statistics and bullet-only check", left, top + box_h + 6, box_w, SMALL)
    paste_fit(page, SCREENSHOT_DIR / "part4_stats_turn5.png", (left + box_w + 24, top, left + 2 * box_w + 24, top + box_h))
    caption(draw, "Turn 5 statistics", left + box_w + 24, top + box_h + 6, box_w, SMALL)
    y = top + box_h + 42
    y = draw_wrapped(draw, "Conceptual answers: prior history is resent because the chat API is stateless between requests; a system prompt sets global behavior while a user message supplies the current request; input tokens grow because earlier conversation messages are sent again on each turn; growth is eventually limited by the model context window and practical latency and memory constraints.", MARGIN, y, BODY_W, BODY)
    y += 16
    bullets = [
        "AI use disclosure is recorded in reports/hw01/AI_USE.md.",
        "The reproducibility and verification summary lives in reports/hw01/verification.json and the self-check script scripts/verify_hw01.py.",
        "The final PDF for submission is reports/hw01/report.pdf.",
    ]
    y = draw_bullets(draw, bullets, MARGIN, y, BODY_W, BODY)
    pages.append(page)

    return pages


def main() -> int:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    pages = build_pages()
    page_paths = []
    for idx, page in enumerate(pages, start=1):
        path = TEMP_DIR / f"page-{idx}.png"
        page.save(path)
        page_paths.append(path)

    # Assemble a multi-page PDF from the rendered page images.
    images = [Image.open(path).convert("RGB") for path in page_paths]
    first, rest = images[0], images[1:]
    first.save(OUTPUT_PDF, save_all=True, append_images=rest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
