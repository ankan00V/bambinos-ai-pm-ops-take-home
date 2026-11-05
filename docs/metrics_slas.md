# Metrics and SLAs

Eight metrics, defined so that a person can compute each one from the same files without asking me. Baseline means the value in this dataset at 2026-11-03 18:00. Target means the value the redesigned flow should hold in steady state. Owner means the role accountable when the metric breaches.

## The eight metrics

**1. Orphaned Invoice Rate**

Formula: money-received invoices with zero form rows divided by money-received invoices.
Baseline: 2 of 12, **16.7%**. Value INR 29,000.
Target: **under 2%**, which in the new flow should only happen when a payment cannot be attributed to a student at all.
Owner: ops_agent. Reviewed daily.

**2. Payment-to-Schedule Turnaround**

Formula: hours from `paid_at` to the `created_at` of the first `classschedulebookings` row for that invoice. Median and 90th percentile, not mean, because one stuck case distorts a mean.
Baseline: **1.75 hours on 1 sample**. That is an anecdote, not a baseline. The usable baseline is the censored view: 11 of 12 paid renewals had no schedule row at the snapshot, and the oldest had waited 51.7 hours.
Target: **median under 15 minutes, p90 under 4 hours**. Fifteen minutes is achievable because no human is in the loop for the happy path. Four hours is the p90 because batch changes and identity checks need a parent reply.
Owner: ops_agent, with ops_lead accountable for the p90.

**3. Form Submission Lag**

Formula: hours from `paid_at` to the form's `created_at`.
Baseline: median **27.1 minutes**, n=10, range 14.8 to 49.8.
Target: **not applicable in the new flow** for same-batch renewals, because no form is required. Tracked only for batch changes, where it becomes Parent Selection Lag.
Owner: teacher, for the legacy flow during shadow mode.

**4. Approval Lag**

Formula: hours from the form's `created_at` to `approved_at`.
Baseline: median **1.54 hours** across the 4 approved forms, but **8 of 12 forms were unapproved**, aged 5.2 to 32.5 hours. Reporting only the median hides the queue.
Target: **under 5 minutes for auto-approved cases**, under 4 hours for exceptions.
Owner: ops_agent.

**5. Unscheduled Booking Rate**

Formula: booking requests with zero schedule rows divided by all booking requests.
Baseline: 3 of 4, **75%**. Two of those were approved and paid.
Target: **under 5%**, measured at 24 hours after approval so a booking created minutes ago does not count as a failure.
Owner: ops_agent.

**6. First-Pass Auto-Approval Rate**

Formula: renewal cases that reach a booking with no human edit divided by all renewal cases.
Baseline: **0%**. Every one of the 12 forms carries either an `approved_by` value or no approval at all. Nothing in the current flow can approve itself.
Target: **70%**, with 66.7% demonstrated on this dataset.
Owner: Head of Ops.

**7. Exception Resolution Time**

Formula: hours from the moment a case enters an exception state to the moment it leaves. While a case is open, report open age.
Baseline: median open age of the 6 blocking exceptions is **29.7 hours**, worst case 51.7 hours.
Target: **median under 4 hours, p90 under 24 hours**, matching the per-code SLAs below.
Owner: the assigned owner, escalated to ops_lead at SLA.

**8. Class Interruption Rate**

Formula: students with money received and no future, non-cancelled session row divided by students with money received.
Baseline: 11 of 12, **91.7%**, covering INR 126,850 of the INR 138,850 collected.
Target: **under 2%**. A child with a settled renewal should never have an empty calendar.
Owner: Head of Ops. This is the metric the whole redesign exists to move.

Two supporting counters, not headline metrics:

- **Stuck Invoice Rate over 12 hours**: 6 of 12 paid invoices, 50%. This is the dashboard tile the ops head asked for.
- **Zero Touch Eligible Rate**: 8 of 12 paid invoices, 66.7%. This says how much of the queue never needs a human, independent of what the engine actually pushed today.

## SLA table by reason code

First response is the time to acknowledge and start. Resolution is the time to clear. Escalation happens automatically at the SLA, not when someone remembers.

| Code | Meaning | Owner | First response | Resolve | Escalates to |
| --- | --- | --- | --- | --- | --- |
| R02 | Invoice reference unresolved | teacher | 4h | 24h | ops_lead |
| R04 | Duplicate form | teacher | 24h | 24h | ops_lead |
| R05 | Claimed amount differs from collected | finance | 4h | 8h | ops_lead |
| R06 | Part payment | finance | 4h | 24h | ops_lead |
| R07 | Payment not completed | parent | 24h | 48h | ops_lead |
| R08 | Batch at capacity | ops_agent | 4h | 8h | ops_lead |
| R09 | Batch change requested | parent | 8h | 24h | ops_lead |
| R10 | Student missing from reference | ops_agent | 4h | 8h | ops_lead |
| R11 | Student identity mismatch | ops_agent | 4h | 8h | ops_lead |
| R12 | Payer contact mismatch | ops_agent | 4h | 4h | ops_lead |
| R13 | Teacher mismatch | ops_agent | 4h | 8h | ops_lead |
| R14 | Class mismatch | ops_agent | 4h | 8h | ops_lead |
| R15 | Stale batch on form | ops_agent | 4h | 8h | ops_lead |
| R16 | Invalid session count | teacher | 8h | 24h | ops_lead |
| R18 | Cross border payment | finance | 24h | 72h | ops_lead |
| R19 | Fee variance | finance | 8h | 24h | ops_lead |
| R20 | Approved but never scheduled | ops_agent | 4h | 8h | ops_lead |
| R21 | Approved with no booking | ops_agent | 4h | 8h | ops_lead |
| R22 | Discount applied | finance | none | 7 days | none |
| R23 | Batch missing from reference | ops_agent | 4h | 8h | ops_lead |
| R24 | Form rejected earlier | teacher | 8h | 24h | ops_lead |

## Escalation ladder

| Level | Role | Trigger | Authority |
| --- | --- | --- | --- |
| 1 | Assigned owner | Case enters the queue | Can resolve within policy |
| 2 | ops_lead | SLA breached, or value above INR 15,000 | Can reassign, can approve a seat override with teacher consent |
| 3 | Head of Operations | Breach over 24 hours, or any case where a child misses a scheduled class | Can approve refunds, credits and batch creation |
| 4 | Finance lead | Any payment dispute or chargeback | Owns gateway reconciliation |

The escalation is a clock, not a judgement call. The engine stamps `sla_hours` on every row, the dashboard counts down against it, and the daily digest names anything past due. No one has to decide whether a case is late.

## What is deliberately not an SLA

- **Teacher response time.** Teachers are contractors paid per class. An SLA on their admin work would need a contract change, so the design removes the admin instead of policing it.
- **Parent response time.** A parent who has paid and stopped replying is not a process failure. Those cases move to a "waiting on parent" state with a 48 hour nudge, and they do not count against Ops.
- **Time to first class.** It depends on the batch calendar, not on Ops. Measuring it would blame the wrong team.
