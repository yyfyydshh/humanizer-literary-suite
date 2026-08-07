#!/usr/bin/env python3
"""Validate independent literary reviews and compute the delivery gate."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REQUIRED_ROLES = {"style_fidelity", "ai_language", "narrative_integrity", "cold_reader"}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalize_reviews(paths: list[Path]) -> list[dict]:
    reviews: list[dict] = []
    for path in paths:
        payload = load_json(path)
        if isinstance(payload, list):
            reviews.extend(payload)
        elif isinstance(payload, dict) and isinstance(payload.get("reviews"), list):
            reviews.extend(payload["reviews"])
        elif isinstance(payload, dict):
            reviews.append(payload)
        else:
            raise ValueError(f"unsupported review payload: {path}")
    return reviews


def validate_review(review: dict, allowed_roles: set[str]) -> None:
    role = review.get("role")
    if role not in allowed_roles:
        raise ValueError(f"invalid role: {role}")
    for key in ("ai_risk", "confidence"):
        value = review.get(key)
        if not isinstance(value, (int, float)) or not 0 <= value <= 100:
            raise ValueError(f"{role}.{key} must be within 0..100")
    if not isinstance(review.get("evidence", []), list):
        raise ValueError(f"{role}.evidence must be a list")
    if role == "narrative_integrity" and not isinstance(review.get("integrity_pass"), bool):
        raise ValueError("narrative_integrity.integrity_pass must be boolean")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews", nargs="+", required=True, type=Path)
    parser.add_argument("--integrity", required=True, type=Path, help="integrity_check.py JSON output")
    parser.add_argument("--semantic-pass", action="store_true", help="Assert the separate semantic audit passed")
    parser.add_argument("--arbitration", type=Path)
    parser.add_argument("--round", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    try:
        reviews = normalize_reviews(args.reviews)
        for review in reviews:
            validate_review(review, REQUIRED_ROLES)
        roles = [review["role"] for review in reviews]
        if set(roles) != REQUIRED_ROLES or len(roles) != len(REQUIRED_ROLES):
            raise ValueError(f"expected exactly one review for each role: {sorted(REQUIRED_ROLES)}")
        integrity = load_json(args.integrity)
        hard_pass = bool(integrity.get("hard_pass"))
        narrative = next(review for review in reviews if review["role"] == "narrative_integrity")
        narrative_pass = bool(narrative.get("integrity_pass")) and not narrative.get("integrity_issues", [])
        base_scores = [float(review["ai_risk"]) for review in reviews]
        spread = max(base_scores) - min(base_scores)
        needs_arbitration = spread > 20
        arbitration = None
        scores = list(base_scores)
        if args.arbitration:
            arbitration = load_json(args.arbitration)
            validate_review(arbitration, {"arbitrator"})
            scores.append(float(arbitration["ai_risk"]))
        if needs_arbitration and arbitration is None:
            status = "needs_arbitration"
            risk = statistics.median(base_scores)
            accepted = False
        else:
            risk = statistics.median(scores)
            accepted = risk <= 20 and hard_pass and args.semantic_pass and narrative_pass
            status = "pass" if accepted else ("stop_integrity_first" if not (hard_pass and args.semantic_pass and narrative_pass) else "revise")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    payload = {
        "schema_version": "1.0",
        "round": args.round,
        "review_scores": {review["role"]: review["ai_risk"] for review in reviews},
        "review_confidence": {review["role"]: review["confidence"] for review in reviews},
        "score_spread": spread,
        "arbitration_required": needs_arbitration,
        "arbitration_score": arbitration["ai_risk"] if arbitration else None,
        "ai_risk_median": risk,
        "threshold": 20,
        "hard_integrity_pass": hard_pass,
        "semantic_integrity_pass": bool(args.semantic_pass),
        "narrative_integrity_pass": narrative_pass,
        "accepted": accepted,
        "status": status,
        "disclaimer": "This is a heuristic AI-trace risk score, not a measurement of actual AI participation or authorship.",
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
