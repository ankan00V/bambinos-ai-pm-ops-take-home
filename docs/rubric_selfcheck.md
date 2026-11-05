# Rubric self check

The four rubric dimensions, what I built for each, and where to look.

| Dimension | Weight | What I built | Where |
| --- | --- | --- | --- |
| Problem discovery and edge cases | 25% | Every hypothesis in the brief tested with a count and a denominator, including the ones that produced zero. Five failure modes the brief did not list, each with evidence. Join reliability ranked by actual match rates. | `docs/findings.md`, `docs/data_profile.md`, `outputs/decisions.csv` |
| Process re-engineering | 25% | The form is eliminated as a trigger for clean renewals, with the arithmetic that justifies it. Fast lane defined by four conditions. Five exception types with owners, SLAs and escalation. Change management and rollback in the report. | `README.md`, `docs/metrics_slas.md`, `report/report.pdf` sections B and D |
| AI and no-code execution | 25% | Working Python engine, 31 tests across every reason code, n8n export with an embedded rules mirror, a Google Sheets formula spec, three prompt files, drafted messages in two channels with template fallback. | `engine/`, `workflows/`, `prompts/`, `outputs/` |
| Data, SLAs and ownership | 25% | Eight metrics with formulas, baselines and targets. Per-code SLA table and a four level escalation ladder. Editable savings model with sensitivity. Dashboard built from real outputs. | `docs/metrics_slas.md`, `outputs/savings_model.csv`, `dashboard/dashboard.html` |

## Specific rubric phrases and where they are answered

**Orphaned invoices.** 2 of 12, INR 29,000. `docs/findings.md` section 4, `outputs/invoice_status.csv`.

**Teacher delays.** Median 27.1 minutes payment to form, n=10. `docs/findings.md` section 5.

**ID mismatches.** 84904 paid from a number and email that match neither the registered contact. Held for one call. `docs/findings.md` section 4, `outputs/exceptions.csv` row R12.

**Same-batch fast tracking.** 11 of 12 forms are same-batch, and the preferred time equals the existing batch time in all 11. `docs/findings.md` section 6.

**Questioning why manual steps exist.** `report/report.pdf` section B, plus README design decisions. The approval step is shown to take the same minute as booking creation, so it is not the bottleneck.

**Smart exception handling with the right person.** `outputs/messages.csv` has one row per audience with recipient, channel and escalation. `docs/metrics_slas.md` maps each code to an owner and an SLA.

**Working prototype that reconciles messy records.** `python3 engine/run.py`, then read `outputs/decisions.csv`. The messy cases are 84931 to 84913, 84908 submitted twice, 84904 paid from another number, 84907 discounted, 84909 half paid, 84911 failed.

**Realistic time and cost savings.** `outputs/savings_model.csv` shows every line item, `engine/savings_assumptions.json` is the editable input, and the report shows a 55, 70 and 80 percent sensitivity.

**Dashboard design.** `dashboard/dashboard.html` with a screenshot at `dashboard/screenshots/dashboard.png`, six tiles including stuck over 12h, unapproved forms, unscheduled bookings and hours saved.

**SOP for non-tech teams.** `docs/sop_teachers.md` and `docs/sop_ops.md`, both written for the person doing the job, not for a reviewer.

**30-60-90, rollback, live schedule safety.** `report/report.pdf` section D.

## Honest gaps

- The report's interruption rate rests on a two row schedule table. Flagged in the report, the findings and the README.
- The LLM message path has never run against a real key. The fallback is what produced the shipped messages.
- The n8n workflow is structurally validated and its JavaScript passes a syntax check, but it has not been imported into a live n8n instance, because no instance was available.
- The Google Sheets spec has not been pasted into a sheet. The formulas are written against the real column letters of the provided CSVs, and the one formula that is fragile, the stuck invoice `SUMPRODUCT`, is called out in the doc.
