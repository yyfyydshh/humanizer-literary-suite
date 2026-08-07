#!/usr/bin/env python3
"""Deterministic, privacy-conscious style metrics for literary text samples."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?])(?:[”’』」])?\s*")
TEXT_CHARS = re.compile(r"[\u3400-\u9fffA-Za-z0-9]")
NUMBER_RE = re.compile(
    r"\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千万亿]+"
    r"(?:岁|年|月|日|天|点|分|秒|元|块|角|斤|米|厘米|次|圈|层|楼|路|号|度|篇|章|页|杯|瓶|包|颗|粒)"
)
PATTERNS = {
    "negative_contrast": re.compile(r"不是.{0,32}(?:而是|只是|是)"),
    "explanatory_echo": re.compile(r"(?:这意味着|这就是|也就是说|换句话说|本质上|他知道|她知道|终于明白|这才意识到)"),
    "soft_adverbs": re.compile(r"(?:仿佛|犹如|宛若|如同|一丝|一抹|些许|几分|隐约|缓缓|微微|轻轻|淡淡)"),
    "suddenness": re.compile(r"(?:突然|瞬间|下一秒|那一秒|立刻|此刻|紧接着|骤然)"),
    "formulaic_ending": re.compile(r"(?:这一刻|这就是|终于明白|原来如此|一切都)"),
    "teacher_voice": re.compile(r"(?:说明什么[？?]|这叫什么[？?]|看明白了吗|你以为.{0,24}(?:其实|实际上))"),
}


def extract_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        data = archive.read("word/document.xml")
    root = ET.fromstring(data)
    paragraphs: list[str] = []
    for paragraph in root.iter(W_NS + "p"):
        text = "".join(node.text or "" for node in paragraph.iter(W_NS + "t"))
        if text.strip():
            paragraphs.append(text)
    return "\n\n".join(paragraphs)


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return extract_docx(path)
    if suffix not in {".txt", ".md"}:
        raise ValueError(f"unsupported format: {path.suffix}")
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("text", raw, 0, len(raw), "unable to detect encoding")


def content_length(value: str) -> int:
    return len(TEXT_CHARS.findall(value))


def percentile(values: list[int], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * ratio
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    fraction = index - low
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def analyze(texts: list[str], labels: list[str]) -> dict:
    joined = "\n\n".join(texts)
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n|\r?\n", joined) if part.strip()]
    sentences = [s.strip() for s in SENTENCE_SPLIT.split(joined) if s.strip()]
    lengths = [content_length(s) for s in sentences if content_length(s)]
    dialogue_sentences = [s for s in sentences if re.search(r"[“”‘’『』「」\"']", s)]
    punctuation = Counter(ch for ch in joined if ch in "，。！？；：、…—“”‘’「」『』")
    number_tokens = NUMBER_RE.findall(joined)
    pronouns = {key: joined.count(key) for key in ("我", "我们", "他", "她", "他们", "她们", "你")}
    pattern_counts = {name: len(regex.findall(joined)) for name, regex in PATTERNS.items()}
    total_chars = content_length(joined)

    return {
        "schema_version": "1.0",
        "files": labels,
        "file_count": len(texts),
        "character_count": total_chars,
        "paragraph_count": len(paragraphs),
        "sentence_count": len(sentences),
        "sentence_length": {
            "mean": round(statistics.mean(lengths), 2) if lengths else 0,
            "median": round(statistics.median(lengths), 2) if lengths else 0,
            "p90": round(percentile(lengths, 0.9), 2),
            "short_ratio_le_8": round(sum(x <= 8 for x in lengths) / len(lengths), 4) if lengths else 0,
            "long_ratio_ge_35": round(sum(x >= 35 for x in lengths) / len(lengths), 4) if lengths else 0,
        },
        "average_paragraph_chars": round(
            sum(content_length(p) for p in paragraphs) / len(paragraphs), 2
        ) if paragraphs else 0,
        "dialogue_sentence_ratio": round(len(dialogue_sentences) / len(sentences), 4) if sentences else 0,
        "punctuation_counts": dict(punctuation),
        "pronoun_counts": pronouns,
        "number_token_count": len(number_tokens),
        "number_density_per_1000_chars": round(len(number_tokens) * 1000 / total_chars, 2) if total_chars else 0,
        "signal_counts": pattern_counts,
        "privacy_note": "No source text or excerpts are included in this metrics file.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--stdin", action="store_true", help="Read one UTF-8 sample from stdin")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    if not args.files and not args.stdin:
        parser.error("provide files or --stdin")

    texts: list[str] = []
    labels: list[str] = []
    try:
        for path in args.files:
            texts.append(read_text(path))
            labels.append(path.name)
        if args.stdin:
            texts.append(sys.stdin.read())
            labels.append("<stdin>")
        payload = analyze(texts, labels)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
