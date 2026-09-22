"""Build eval/labels.json — the ground truth the parser is scored against.

Sources, in order of trust:
  1. data/training/batch_0001/reviews.json entries marked "approved"
  2. eval/labels_manual.json — hand-written or reviewed labels keyed by file hash

`draft_answers` in examples.jsonl is the PARSER'S OWN OUTPUT. It is never used
as ground truth: scoring a parser against its own output measures nothing and
would report near-100% accuracy no matter how wrong it is.

    python eval/make_labels.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
from scoring import FIELDS  # noqa: E402

EXAMPLES = ROOT / "data" / "training" / "batch_0001" / "examples.jsonl"
REVIEWS = ROOT / "data" / "training" / "batch_0001" / "reviews.json"
MANUAL = ROOT / "eval" / "labels_manual.json"
OUT = ROOT / "eval" / "labels.json"
CV_FOLDER = ROOT / "Transfered Cv Data"


def load_examples() -> dict[str, dict]:
    if not EXAMPLES.exists():
        return {}
    examples = {}
    for line in EXAMPLES.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            examples[record["file_hash"]] = record
    return examples


def main() -> int:
    examples = load_examples()
    labels: dict[str, dict] = {}
    counts = {"reviews": 0, "manual": 0, "no_text": 0, "rejected_empty": 0}

    if REVIEWS.exists():
        for file_hash, review in json.loads(REVIEWS.read_text(encoding="utf-8")).items():
            answers = review.get("answers") or {}
            if review.get("review_status") != "approved" or not any(answers.values()):
                counts["rejected_empty"] += 1
                continue
            example = examples.get(file_hash, {})
            labels[file_hash] = {
                "source_file": example.get("source_file", ""),
                "text": example.get("text", ""),
                "labelled_by": review.get("reviewed_by", "reviews.json"),
                "notes": review.get("review_notes", ""),
                "fields": {field: answers.get(field, "") for field in FIELDS},
            }
            counts["reviews"] += 1

    if MANUAL.exists():
        for file_hash, entry in json.loads(MANUAL.read_text(encoding="utf-8")).items():
            example = examples.get(file_hash, {})
            source_file = entry.get("source_file") or example.get("source_file", "")
            candidate = CV_FOLDER / source_file if source_file else None
            labels[file_hash] = {
                "source_file": source_file,
                "file_path": str(candidate) if candidate and candidate.is_file() else "",
                "text": entry.get("text") or example.get("text", ""),
                "labelled_by": entry.get("labelled_by", "manual"),
                "notes": entry.get("notes", ""),
                "fields": {field: entry.get("fields", {}).get(field, "") for field in FIELDS},
            }
            counts["manual"] += 1

    for entry in labels.values():
        if not entry.get("text"):
            counts["no_text"] += 1

    OUT.write_text(json.dumps({
        "schema": 1,
        "warning": "Assistant-reviewed labels are not human-certified ground truth.",
        "labels": labels,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"labels written: {len(labels)} -> {OUT}")
    print(f"  from reviews.json (approved): {counts['reviews']}")
    print(f"  from labels_manual.json:      {counts['manual']}")
    print(f"  skipped (not approved/empty): {counts['rejected_empty']}")
    print(f"  entries with no stored text:  {counts['no_text']}")
    if len(labels) < 25:
        print(f"\n  WARNING: {len(labels)} labelled CVs is too few to measure anything.")
        print("  Per-field accuracy from this sample has a margin of error near +/-20 points.")
        print("  Target 100+ before trusting any comparison between variants.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
