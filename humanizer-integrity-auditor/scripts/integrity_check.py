#!/usr/bin/env python3
"""Run deterministic hard checks before semantic literary integrity review."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NUMBER_RE = re.compile(
    r"\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千万亿]+"
    r"(?:岁|年|月|日|天|点|分|秒|元|块|角|斤|米|厘米|次|圈|个|层|楼|路|号|度|篇|章|页|人|只|本|张|份|杯|瓶|包|颗|粒)"
)


def extract_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs: list[str] = []
    for paragraph in root.iter(W_NS + "p"):
        value = "".join(node.text or "" for node in paragraph.iter(W_NS + "t"))
        if value.strip():
            paragraphs.append(value)
    return "\n\n".join(paragraphs)


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        return extract_docx(path)
    if path.suffix.lower() not in {".txt", ".md"}:
        raise ValueError(f"unsupported format: {path.suffix}")
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"unable to decode: {path}")


def paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n|\r?\n", text) if part.strip()]


def first_nonempty(text: str) -> str:
    values = paragraphs(text)
    return values[0] if values else ""


def last_nonempty(text: str) -> str:
    values = paragraphs(text)
    return values[-1] if values else ""


def check_item(name: str, passed: bool, expected=None, actual=None, severity="hard") -> dict:
    return {
        "name": name,
        "passed": bool(passed),
        "severity": severity,
        "expected": expected,
        "actual": actual,
    }


def sequence_summary(expected: list[str], actual: list[str]) -> tuple[dict, dict]:
    first_difference = None
    for index, (left, right) in enumerate(zip(expected, actual)):
        if left != right:
            first_difference = {"index": index, "expected": left, "actual": right}
            break
    if first_difference is None and len(expected) != len(actual):
        first_difference = {
            "index": min(len(expected), len(actual)),
            "expected": expected[min(len(expected), len(actual))] if len(expected) > len(actual) else None,
            "actual": actual[min(len(expected), len(actual))] if len(actual) > len(expected) else None,
        }
    return (
        {"count": len(expected), "first_difference": first_difference},
        {"count": len(actual), "first_difference": first_difference},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--revised", required=True, type=Path)
    parser.add_argument("--lock", type=Path, help="JSON content lock")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    try:
        original = read_text(args.original)
        revised = read_text(args.revised)
        lock = json.loads(args.lock.read_text(encoding="utf-8-sig")) if args.lock else {}
    except (OSError, ValueError, json.JSONDecodeError, KeyError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    checks: list[dict] = []
    checks.append(check_item("revised_not_empty", bool(revised.strip()), True, bool(revised.strip())))

    expected_title = lock.get("title", "")
    if expected_title:
        checks.append(check_item("title_preserved", first_nonempty(revised) == expected_title, expected_title, first_nonempty(revised)))

    original_numbers = NUMBER_RE.findall(original)
    revised_numbers = NUMBER_RE.findall(revised)
    expected_summary, actual_summary = sequence_summary(original_numbers, revised_numbers)
    checks.append(check_item(
        "number_sequence_preserved",
        original_numbers == revised_numbers,
        expected_summary,
        actual_summary,
    ))

    for name in lock.get("protected_names", []):
        if name and name in original:
            checks.append(check_item(f"protected_name:{name}", name in revised, "present", "present" if name in revised else "missing"))

    for phrase in lock.get("required_phrases", []):
        if phrase:
            checks.append(check_item(f"required_phrase:{phrase[:20]}", phrase in revised, phrase, "present" if phrase in revised else "missing"))

    quote_pairs = [("“", "”"), ("‘", "’")]
    for left, right in quote_pairs:
        counts = (revised.count(left), revised.count(right))
        checks.append(check_item(f"balanced_quotes:{left}{right}", counts[0] == counts[1], "equal counts", counts))
    legacy_count = sum(revised.count(char) for char in "「」『』")
    checks.append(check_item("no_legacy_corner_quotes", legacy_count == 0, 0, legacy_count))

    original_paragraphs = paragraphs(original)
    revised_paragraphs = paragraphs(revised)
    delta = abs(len(original_paragraphs) - len(revised_paragraphs))
    allowance = max(1, round(len(original_paragraphs) * 0.1))
    checks.append(check_item(
        "paragraph_count_reasonable",
        delta <= allowance,
        len(original_paragraphs),
        len(revised_paragraphs),
        severity="warning",
    ))
    checks.append(check_item(
        "ending_text_changed",
        last_nonempty(original) == last_nonempty(revised),
        last_nonempty(original),
        last_nonempty(revised),
        severity="warning",
    ))

    hard_failures = [item for item in checks if item["severity"] == "hard" and not item["passed"]]
    warnings = [item for item in checks if item["severity"] == "warning" and not item["passed"]]
    payload = {
        "schema_version": "1.0",
        "original": str(args.original),
        "revised": str(args.revised),
        "hard_pass": not hard_failures,
        "semantic_review_required": True,
        "checks": checks,
        "hard_failures": [item["name"] for item in hard_failures],
        "warnings": [item["name"] for item in warnings],
        "note": "Hard checks do not prove plot or emotional integrity; complete the semantic audit.",
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0 if payload["hard_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
