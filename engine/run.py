import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.pipeline import describe, run


def main():
    parser = argparse.ArgumentParser(description="Reconcile renewal invoices, teacher forms and class schedules.")
    parser.add_argument("--data-dir", default=None, help="Folder holding the five CSVs")
    parser.add_argument("--out-dir", default=None, help="Folder for the generated outputs")
    parser.add_argument("--llm", action="store_true", help="Rewrite drafts with the LLM, template fallback if no key")
    parser.add_argument("--quiet", action="store_true", help="Suppress the console summary")
    args = parser.parse_args()

    summary = run(args.data_dir, args.out_dir, args.llm)
    if not args.quiet:
        print(describe(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
