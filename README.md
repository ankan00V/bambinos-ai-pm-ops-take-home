# Bambinos renewal reconciliation engine

A working prototype that takes the four renewal tables, decides which paid renewals can be scheduled without a human, flags the rest with a reason code, owner, SLA and a drafted message, and writes the four files the assessment asks for.

The finding it is built on: the payment record already holds every field needed to schedule a same-batch renewal. The teacher form adds a preferred time that in this data is identical to the student's existing batch. So the form stops being the trigger and becomes optional corroboration, and the 27 minute wait, the 16.7% of paid invoices with no form, and the invoice typo class all disappear.

## Run it in three commands

```
python3 engine/run.py
python3 -m pytest engine/tests
python3 dashboard/build_dashboard.py
```

No install step. The engine is standard library only. `engine/requirements.txt` lists pytest, which is the only test dependency.

Optional:

```
python3 engine/profile.py
python3 engine/charts.py
python3 engine/run.py --llm
```

`--llm` rewrites the drafted messages with the prompt in `prompts/draft_message.md` if `OPENAI_API_KEY` is set. Without a key, or if the call fails, every message falls back to its deterministic template. The shipped outputs were produced without a key, so `summary.json` reports `"llm_used": false`. That is the intended default, not a failure.

## What comes out

| File | Contents |
| --- | --- |
| `outputs/auto_approved.csv` | Rows ready for `class_schedule_bookings`, with batch, sessions, seat count after approval and a readable reason |
| `outputs/exceptions.csv` | One row per flagged case with reason code, severity, blocking flag, owner, escalation, SLA, hours open, recommended action and reason |
| `outputs/messages.csv` and `messages.md` | Drafted WhatsApp and Slack messages per exception, addressed to the right person, with the number that triggered it |
| `outputs/summary.json` | Counts, auto-approval rate, exceptions by reason and owner, metric baselines, savings, limits |
| `outputs/invoice_status.csv` | One row per invoice: stage, hours since payment, sessions scheduled, interruption risk |
| `outputs/decisions.csv` | Full decision log, including rows that were not approved or flagged |

## Results on the provided data

Data as of 2026-11-03 18:00, the latest timestamp in the files.

| Measure | Value |
| --- | --- |
| Renewal cases | 13 |
| Auto-approved with no human | 6, 46.2% of cases |
| Zero-touch eligible | 8 of 12 paid invoices, 66.7% |
| Blocking exceptions | 6 |
| Informational rows | 1 duplicate form |
| Already scheduled | 1 |
| Paid invoices with no form | 2, 16.7%, INR 29,000 |
| Paid renewals with no future class | 11 of 12, 91.7%, INR 126,850 |
| Payment to form, median | 27.1 minutes, n=10 |
| Form to approval, median | 1.54 hours, n=4 |
| Payment to first session | 1.75 hours, n=1 |
| Hours saved per month | 155.2 at 1,000 renewals, base case |
| Cost saved per month | INR 46,557 at INR 300 per ops hour |

The six exceptions are R20 approved but never scheduled, R12 payer contact mismatch, R08 batch at capacity, R09 batch change, R06 part payment, R07 payment not completed.

`auto_approval_rate` is 46.2% because this snapshot includes a failed payment, an already scheduled case, and four cases that genuinely need a human. The forward-looking number is the zero-touch rate of 66.7%, which counts cases that would clear with no human if the engine ran from a clean state.

## Design decisions

**The invoice is the trigger, the form is evidence.** Every rule reads the invoice and the active reference first. The form is used only to corroborate and to carry a batch-change request. In the data, two paid invoices had no form at all and were still fully schedulable.

**Deterministic first, LLM last.** Every decision is a rule with a reason code. The LLM only rewrites message copy, and only when a key is present. Fuzzy matching is limited to one job: repairing a mistyped invoice reference, with a similarity floor of 0.72, a margin of 0.05 over the runner-up, and a hard requirement that the student and the amount already match. A wrong invoice moves money onto the wrong child, so the matcher prefers refusing.

**Score the invoice number, not the link.** Two invoice URLs differ in three characters out of fifty, so whole-string similarity scores a wrong invoice at 0.97. The engine extracts the number and scores that. This was caught by a test, not by inspection.

**Net amount, not gross.** Form 3307 claims 7,600 against a 9,500 list price. The invoice carries a 1,900 discount, exactly 20%, so the renewal is clean. Comparing claims to gross would produce a false exception on every discounted renewal.

**Blocking versus informational.** A reason code either stops scheduling or it does not. R04 duplicate and R18 cross-border are informational. R12 payer mismatch blocks, because the payment's contact details match nothing on file and a two minute call settles it.

**Seats are a ledger, not a lookup.** Approvals are processed in invoice order and each one decrements the batch. Two renewals into the last free seat cannot both pass. The reference count alone would let them.

**Idempotent by construction.** No wall clock in any output, deterministic ordering, and a state check that skips cases which already have session rows. `test_run_is_idempotent` compares bytes across two runs.

**Explainability over coverage.** Each row carries a sentence with the actual numbers, for example "Batch 9205 (CM-G4-Batch-D) is at 6 of 6 seats. INR 11,000 cleared 28.8 hours ago". An ops person can read the CSV without opening the code.

## Repo layout

```
data/                   the five CSVs, copied from ops/data in the assessment repo
engine/                 reconciliation engine, profiling, charts, tests
prompts/                the three LLM prompts, exactly as used
outputs/                generated results
workflows/              n8n export and a Google Sheets formula spec
dashboard/              static dashboard and its screenshot
docs/                   findings, metrics and SLAs, SOPs, cheat sheet, Loom script
report/                 report source, charts and the PDF
```

## Tests

31 tests cover every reason code from R00 to R24, the phone and email normalizers, the invoice reference parser, the fuzzy tie-break, idempotency, and the rule that every blocking exception has an owner, an SLA and a message. Fixtures are built by copying the real CSVs and mutating one row, so the tests exercise the same schema as production.

## Limitations

- **The schedule export is thin.** Two rows for twelve paid renewals. Either eleven students genuinely have no class, or the export is partial. I treat the 91.7% interruption rate as a flag to verify, not a number to publish.
- **Masked identities.** Names and numbers are masked, so fuzzy name matching cannot be validated here. The name score is weak by design and never gates a decision.
- **No gateway call.** Payment status is taken from the invoice row. A late settlement or a chargeback is invisible to the engine.
- **Volume is an assumption.** 13 cases over three days is a sample. The savings model runs at 1,000 renewals per month and every input is in `engine/savings_assumptions.json`.
- **The n8n mirror is close but not identical.** It lacks the seat ledger and its message copy is shorter, because a Code node is the wrong place for the full template set. The Python engine is the reference implementation.
- **The LLM path is unexercised in this repo.** No key was available, so the fallback templates are what produced `outputs/messages.csv`. The integration is real but its output has not been reviewed.
