# Bambinos.live — AI Program Manager (Operations) submission

## What to review first

1. `report/report.pdf` — the case report: leakage audit, zero-touch redesign, exception operations, dashboard, SOPs, and 30-60-90 rollout.
2. `README.md` — a concise overview, reproducible commands, the results, design choices, and explicit limitations.
3. `outputs/decisions.csv` — the complete, row-level reconciliation log.
4. `dashboard/dashboard.html` — the morning view for the Head of Operations.

## Reproduce the prototype

```bash
python3 engine/run.py
python3 -m pytest engine/tests
python3 dashboard/build_dashboard.py
python3 report/build_report.py
```

The engine uses only the Python standard library. `pytest` is needed only for the test command. The generated output is deterministic; `test_run_is_idempotent` verifies this.

## Submission assets

- Case report: `report/report.pdf`
- Working reconciliation prototype: `engine/`
- Input data and generated decisions: `data/`, `outputs/`
- Exact LLM prompts: `prompts/`
- n8n export and Google Sheets implementation notes: `workflows/`
- SOPs and 2–3 minute walkthrough script: `docs/`

## Honest boundaries

The source data is a 13-case masked snapshot. The report marks the schedule-export limitation, does not present scenario savings as realised savings, and keeps LLM copy generation non-decisional. See `README.md` and the final page of the report for the full limitations.
