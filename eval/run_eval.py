"""Score the CV parser against labelled ground truth.

    python eval/run_eval.py --variant rules
    python eval/run_eval.py --variant llm --limit 25
    python eval/run_eval.py --variant rules --source files

Two sources:
  text  - replay the stored CV text from a labelled example (default). Isolates
          the extraction rules and the model from PDF/DOCX text extraction.
  files - re-read the original PDF/DOCX. Measures the whole pipeline, including
          extraction errors, which is what actually ships.

Everything runs locally. No network call leaves this machine except to Ollama
on 127.0.0.1.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

from cv_parser.pipeline import parse_cv  # noqa: E402
from scoring import FIELDS, compare  # noqa: E402

LABELS_PATH = ROOT / "eval" / "labels.json"


def load_labels(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"No labels at {path}. Run eval/make_labels.py first.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = []
    for key, entry in payload.get("labels", {}).items():
        entry = dict(entry)
        entry["id"] = key
        items.append(entry)
    return items


def text_as_docx(text: str) -> bytes:
    """Wrap stored text as a DOCX so it enters the pipeline unchanged.

    extract_docx joins paragraphs with newlines, so the text the rules see is
    byte-identical to the stored text. This swaps out only the extraction step.
    """
    from docx import Document

    document = Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def run_one(entry: dict, source: str, use_llm: bool) -> dict:
    if source == "text":
        text = entry.get("text") or ""
        if not text.strip():
            return {"error": "no stored text"}
        record = parse_cv(entry.get("source_file", entry["id"]), text_as_docx(text),
                          enable_ocr=False, use_llm=use_llm)
    else:
        path = Path(entry.get("file_path", ""))
        if not path.is_file():
            return {"error": f"file not found: {path}"}
        record = parse_cv(path.name, path.read_bytes(), enable_ocr=True, use_llm=use_llm)
    return {"record": record}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--labels", type=Path, default=LABELS_PATH)
    parser.add_argument("--variant", choices=["rules", "llm"], default="rules",
                        help="rules = deterministic only; llm = rules + local Ollama model")
    parser.add_argument("--source", choices=["text", "files"], default="text")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", type=Path, default=ROOT / "eval" / "results")
    args = parser.parse_args()

    entries = load_labels(args.labels)
    if args.limit:
        entries = entries[:args.limit]
    if not entries:
        sys.exit("No labelled examples to score.")

    use_llm = args.variant == "llm"
    print(f"Scoring {len(entries)} labelled CVs | variant={args.variant} source={args.source}\n")

    rows: list[dict] = []
    started = time.time()
    for index, entry in enumerate(entries, start=1):
        outcome = run_one(entry, args.source, use_llm)
        if "error" in outcome:
            print(f"  [{index}/{len(entries)}] SKIP {entry['id'][:10]}: {outcome['error']}")
            continue
        record = outcome["record"]
        produced = record.export_dict()
        truth = entry["fields"]
        row = {"id": entry["id"], "source_file": entry.get("source_file", ""),
               "confidence": record.confidence, "status": record.processing_status}
        for field in FIELDS:
            strict, lenient, credit = compare(field, truth.get(field, ""), produced.get(field, ""))
            row[f"{field}__strict"] = strict
            row[f"{field}__lenient"] = lenient
            row[f"{field}__credit"] = credit
            row[f"{field}__expected"] = truth.get(field, "")
            row[f"{field}__actual"] = produced.get(field, "")
        row["all_lenient"] = all(row[f"{f}__lenient"] for f in FIELDS)
        rows.append(row)
        mark = "OK " if row["all_lenient"] else "ERR"
        print(f"  [{index}/{len(entries)}] {mark} {entry.get('source_file', entry['id'])[:52]}")

    if not rows:
        sys.exit("Nothing scored.")

    elapsed = time.time() - started
    print(f"\nScored {len(rows)} CVs in {elapsed:.1f}s ({elapsed / len(rows):.2f}s each)\n")

    print(f"{'field':26} {'strict':>8} {'lenient':>9} {'credit':>8}")
    print("-" * 54)
    for field in FIELDS:
        strict = sum(r[f"{field}__strict"] for r in rows) / len(rows)
        lenient = sum(r[f"{field}__lenient"] for r in rows) / len(rows)
        credit = sum(r[f"{field}__credit"] for r in rows) / len(rows)
        print(f"{field:26} {strict:7.1%} {lenient:8.1%} {credit:7.1%}")
    print("-" * 54)
    macro = sum(sum(r[f"{f}__lenient"] for f in FIELDS) for r in rows) / (len(rows) * len(FIELDS))
    every = sum(r["all_lenient"] for r in rows) / len(rows)
    print(f"{'macro field accuracy':26} {macro:>26.1%}")
    print(f"{'CVs with every field right':26} {every:>26.1%}")

    # The review-gate tradeoff: this is the number that decides shipped accuracy.
    print(f"\n{'auto-accept if':26} {'% auto':>8} {'accuracy of those':>19} {'sent to review':>15}")
    print("-" * 72)
    for threshold in (0.0, 0.5, 0.7, 0.8, 0.9):
        auto = [r for r in rows if r["confidence"] >= threshold and r["status"] == "Ready"]
        share = len(auto) / len(rows)
        accuracy = (sum(r["all_lenient"] for r in auto) / len(auto)) if auto else 0.0
        label = "Ready" if threshold == 0.0 else f"Ready & conf>={threshold:.1f}"
        print(f"{label:26} {share:7.1%} {accuracy:18.1%} {1 - share:14.1%}")

    args.out.mkdir(parents=True, exist_ok=True)
    stamp = f"{args.variant}_{args.source}"
    detail = args.out / f"detail_{stamp}.csv"
    with detail.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    errors = [{"id": r["id"], "source_file": r["source_file"], "field": f,
               "expected": r[f"{f}__expected"], "actual": r[f"{f}__actual"]}
              for r in rows for f in FIELDS if not r[f"{f}__lenient"]]
    error_path = args.out / f"errors_{stamp}.csv"
    with error_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "source_file", "field", "expected", "actual"])
        writer.writeheader()
        writer.writerows(errors)

    print(f"\n{len(errors)} field errors -> {error_path}")
    print(f"per-CV detail       -> {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
