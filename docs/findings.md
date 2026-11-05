# Findings from the four tables

Everything below is counted from the five CSVs in `data/`. The snapshot time is 2026-11-03 18:00, which is the latest timestamp anywhere in the files (`4_class_schedule_bookings` row 990101, `updated_at`). Any number that depends on an assumption rather than a count is labelled as an assumption.

Regenerate with `python3 engine/profile.py` and `python3 engine/run.py`.

## 1. What is in the files

| File | Rows | Columns | Primary key | Duplicate keys |
| --- | --- | --- | --- | --- |
| 1_invoices.csv | 13 | 25 | id | 0 |
| 2_faculty_form_unapproved.csv | 12 | 23 | id | 0 |
| 3_booking_requests.csv | 4 | 20 | id | 0 |
| 4_class_schedule_bookings.csv | 2 | 18 | id | 0 |
| reference_active_batches_and_students.csv | 13 | 20 | student_id | 0 |

No key is duplicated anywhere. Every table uses soft deletes through `deleted_at`, and that column is empty in all 44 rows, so nothing in this extract has been deleted.

Value distributions worth knowing before designing rules:

- `payment_status`: 11 Paid, 1 Partially_Paid, 1 Failed.
- `payment_type`: 12 Full, 1 Installment_1_of_2.
- `approval_status`: 4 Approved, 8 Pending. No rejections.
- `request_status`: 1 Completed, 1 Pending_Batch_Allocation, 1 Failed_Batch_Full, 1 Awaiting_Parent_Batch_Selection. Four bookings, four different states, which is a small sample of how varied the queue is.
- `payment_gateway`: 11 Razorpay, 2 Stripe.
- `continue_same_batch`: 11 Yes, 1 No.
- Batch capacity: one batch at 6 of 6. Every other batch sits between 3 and 5 of 6.

## 2. How the tables join

| Join | Key | Result |
| --- | --- | --- |
| invoices to reference | `student_id` | 13 of 13 found. This is the most reliable join in the set. |
| forms to invoices | `invoice_id` | 10 of 12 exact. 1 typo repaired (form 3313 points at 84931, the real invoice is 84913). 1 duplicate pair points at the same invoice. |
| forms to reference | `student_id` | 13 of 13 distinct students found. |
| booking_requests to forms | `faculty_form_id` | 4 of 12 forms have a booking. |
| booking_requests to invoices | `invoice_id` | 4 of 4 valid. |
| schedule to bookings | `bookingrequest_id` | Only booking 5501 has rows. 3 of 4 bookings have no schedule. |
| schedule to invoices | `invoice_id` | 2 of 2 valid, both for invoice 84901. |
| reference to batches | `current_classbatch_id` | 12 distinct batches for 13 students, because two students share batch 9201. |

Reliability ranking, best to worst:

1. `student_id` and `invoice_id` numeric keys. Exact, no nulls, no mismatches.
2. `educator_id`, `class_id` copied across tables. Consistent in every row of this extract.
3. `invoice_link`. Well formed as a URL in all 12 forms, but the number inside it can be wrong. The URL alone must never be treated as a key, because two different invoice URLs share 47 of 50 characters. A naive string similarity on the whole URL scores a wrong invoice at 0.97, which is why the engine scores the extracted number, not the link.
4. `parent_mobile` on the form. Normally a copy of the invoice mobile, but not always (form 3304 gives a different number from its invoice, and the form is the one that matches the parent record).
5. `student_name` and `educator_name`. These are masked (`Aa***v Sh***a`), so name similarity is close to useless here. Two different children with the same surname will score as a partial match. The engine uses names only as weak corroboration and never as a gate.

## 3. The funnel, stage by stage

| Stage | Count | What it means |
| --- | --- | --- |
| Invoices created | 13 | One per renewal attempt in the window. |
| Money actually received | 12 | 11 Paid plus 1 Partially_Paid. Invoice 84911 failed and never collected. |
| Forms raised | 11 | 12 form rows across 11 distinct invoices, because 84908 was submitted twice. |
| Forms approved | 4 | 33% of form rows. |
| Booking requests | 4 | Every approved form produced one booking, all within the same minute as approval. |
| Bookings completed | 1 | One booking out of four reached `Completed`. |
| Students with a class on the calendar | 1 | Only invoice 84901 has schedule rows. |

The drop from 12 paid invoices to 1 scheduled student is the central fact of this dataset. Some of that gap is a partial export, which I address in section 7, but the intermediate states are specific and they are not random: 2 paid invoices never got a form, 2 approved forms produced bookings that never got a seat, 1 batch was full, 1 form claimed a full payment that was half paid.

## 4. Failure modes, counted

Denominators are stated for each row. Where a hypothesis produced zero cases I say so rather than dropping it.

| Failure mode | Count | Denominator | Evidence | Value at risk |
| --- | --- | --- | --- | --- |
| Paid invoice with no form (orphaned) | 2 | 12 money-received invoices, 16.7% | 84906 (GCC, INR 18,000) and 84910 (INR 11,000). Both teachers submitted nothing. | INR 29,000 |
| Form naming an invoice that does not exist | 1 | 12 forms, 8.3% | Form 3313 gives 84931 and a link ending 84931. The real invoice is 84913. | INR 11,500 |
| Malformed invoice URL | 0 | 12 forms | All 12 links match `https://bambinos.live/invoice/BMB-INV-YYYY-NNNNN` | 0 |
| One invoice used in more than one form | 1 | 11 distinct invoices in forms, 9.1% | Forms 3308 and 3309 both point at 84908, created 08:30:00 and 08:35:12. Remark on 3309 says the browser froze. | 0, but a second booking would double-schedule the child |
| Claimed amount differs from amount collected | 1 | 12 forms, 8.3% | Form 3310 claims 10,500 against a net_amount of 5,250. | INR 5,250 underpaid against 24 sessions |
| Part payment | 1 | 13 invoices, 7.7% | 84909, `Installment_1_of_2`, 5,250 of 10,500. | INR 5,250 outstanding |
| Failed payment | 1 | 13 invoices, 7.7% | 84911, status Failed, `gateway_payment_id` is NULL, `paid_at` is NULL, yet a form was submitted claiming payment. | INR 12,000 never collected |
| Payer contact differs from student record | 1 | 12 money-received invoices, 8.3% | 84904 paid from `+91-9844XXXX77` and `ri***u.iy***@gmail.com`. The record has `+91-9844XXXX04` and `su***h.iy***@outlook.com`. Form 3304 gives the 04 number and the remark says the mother paid. | INR 12,000 misattribution risk |
| Student missing from reference | 0 | 13 distinct students | All present | 0 |
| Batch full | 1 | 12 form rows, 8.3% | Batch 9205 at 6 of 6. Booking 5505 failed with `Failed_Batch_Full`. | INR 11,000 sitting without a seat |
| Batch inactive | 0 | 12 batches | `deleted_at` empty everywhere, no inactive flag exists | 0 |
| Same-batch renewal | 11 | 12 forms, 91.7% | `continue_same_batch` Yes | Not a failure, but it is the reason a fast track is worth building |
| Batch change | 1 | 12 forms, 8.3% | Form 3312, wants Sat/Sun 11:00 instead of Wed/Fri 16:30 | INR 9,000 waiting on batch selection |
| Approved booking never scheduled | 2 | 4 bookings, 50% | 5502 `Pending_Batch_Allocation` for 51.7 hours. 5505 `Failed_Batch_Full`. | INR 21,500 |
| Duplicate schedule rows | 0 | 2 schedule rows | Two distinct dates, 2026-11-03 and 2026-11-05 | 0 |
| Weekend delay | 0 measurable | 2 Sunday payments | Both got a form the same day, in 29.6 and 49.8 minutes | 0 |
| Overnight delay | 3 | 8 pending forms | Forms 3303 (32.5h), 3304 (30.0h) and 3307 (22.8h) all crossed at least one night unapproved | INR 27,600 held open |
| Currency mismatch | 0 detectable | 12 money-received invoices | All billed INR. The reference file has no currency column, so correctness cannot be verified. | Unknown |
| Region mismatch | 2 | 12 money-received invoices | 84906 (UAE, +971) and 84908 (US, +1) both paid INR through Stripe | INR 40,000 of cross-border settlement to reconcile |
| Fee variance | 0 | 12 money-received invoices | Every gross amount equals `standard_fee_24_sessions_inr` | 0 |
| Discount applied | 1 | 12 money-received invoices | 84907, 1,900 off 9,500, net 7,600, exactly 20% | INR 1,900 |

### Failure modes that were not on the brief's list

**The batch-full block looks like a counting artefact.** Batch 9205 is at 6 of 6, and student 68105 is one of those six. A renewal means the child continues, so the seat is already theirs. Treating 6 of 6 as full for an existing occupant is how a paying child gets locked out of a class they are already sitting in. Only one case here, so it needs a check against the real capacity rule before anyone changes code, but it is the single cheapest win in the dataset: one policy conversation, one child back in class.

**The teacher form is the only bridge for a payer mismatch, and it is not independent evidence.** On 84904 the invoice carries a mobile number that appears nowhere else, and the form supplies a number that matches the parent record. That looks like helpful corroboration until you notice the teacher typed it from the same WhatsApp conversation that produced the payment. It is not a second source, it is a copy of the same conversation. The engine holds this case for one call instead of auto-approving it.

**Approval is not the bottleneck. Allocation is.** Approval and booking creation happen in the same minute in all four approved cases. Then booking 5502 sits at `Pending_Batch_Allocation` for 51.7 hours, and 5505 fails outright. Building a faster approval inbox would move the wrong number.

**A discount can look like an underpayment.** Form 3307 claims 7,600 against a 9,500 list price. A naive amount check flags it. The invoice records a 1,900 discount, which is exactly 20%, so the claim matches the net amount and the renewal is clean. Any rule that compares the form to the gross amount will produce false exceptions on every scholarship renewal.

**The schedule export is too thin to trust for revenue maths.** Twelve renewals have money. Two schedule rows exist, both for one student. Either the renewal term genuinely has not started for eleven students, which would be a five-alarm operational failure, or the schedule table in this extract is partial. The arithmetic points at the second: booking 5502 was approved at 17:00 on 1 November and its parent has no class row 51.7 hours later, while the system still describes the booking as pending allocation rather than scheduled. I treat the interruption rate as a flag to verify, not a number to publish internally.

## 5. Timing, measured

Only three transitions have enough data to time.

| Transition | Samples | Median | Range |
| --- | --- | --- | --- |
| Payment to form submitted | 10 | 27.1 minutes | 14.8 to 49.8 minutes |
| Form submitted to approved | 4 | 1.54 hours | 0.75 to 2.5 hours |
| Payment to first schedule row | 1 | 1.75 hours | single case |
| Payment to no class at snapshot | 11 | open, 1.2 to 51.7 hours | 11 cases |

The single complete chain, invoice 84901, splits as 29.6 minutes waiting for the teacher, 45 minutes waiting for Ops approval, and 30 minutes waiting for the session rows. Approval took 43% of a 105 minute journey.

Eight of twelve forms were still unapproved at the snapshot, with ages from 5.2 to 32.5 hours. That is the honest shape of approval lag: 1.54 hours when Ops picks it up, unbounded when nobody does.

## 6. What the numbers say about the process

1. The payment record already contains everything needed to schedule a same-batch renewal: student, class, teacher, batch, amount, discount, currency, payer contact. The teacher form adds a preferred day and time, and those are identical to the batch the student is already in for 11 of 12 forms. So for the happy path the form adds no information the system does not already have.
2. The form's real cost is not the typing. It is the 27 minutes of waiting plus the cases where it never arrives at all, which is 2 of 12 here.
3. The biggest single leak is after approval, not before it: two approved bookings worth INR 21,500 never became classes.
4. The queue is small enough to reason about by hand, which means the rules can be audited by an ops person without a data team.

## 7. What this data cannot tell me

I would rather state these than overfit a rule set to 13 rows.

- **Masked identities.** With `Aa***v Sh***a` and `+91-9811XXXX01` I can match exact records but I cannot measure how well fuzzy name matching works on real names. The engine's name score is deliberately weak and never gates a decision.
- **Term boundaries.** There is no term start or end date anywhere. Class interruption is therefore a proxy: money received and no future session row. It cannot distinguish "term ended yesterday" from "term was supposed to start last week".
- **Gateway truth.** The engine trusts `payment_status` on the invoice. It never calls Razorpay or Stripe. A payment that settles after the export, or a chargeback, is invisible.
- **Refunds and credits.** No refund table, so a paid invoice that was later refunded would still look payable.
- **Teacher availability and rosters.** No table says which teachers are active or which batches are closing. The capacity artefact above cannot be resolved from this extract alone.
- **Volume.** 13 cases over three days is a sample, not a rate. Every monthly figure in the savings model is a scenario with an explicit volume assumption.
- **Policy.** There is no written rule for what to do when a parent pays half, or when a discount exceeds 20%. The engine recommends a decision rather than inventing one.

## 8. What this changes about the design

The brief asks whether the teacher form can be eliminated for clean renewals. On this data the answer is yes, and the reason is arithmetic rather than opinion: for 11 of 12 forms, every field except the preferred time is already present and identical in the invoice and reference tables, and the preferred time matches the student's existing batch in all 11. Two renewals had no form at all and were still fully schedulable from the payment record.

So the engine runs the invoice as the trigger and treats the form as optional corroboration. That single change removes the 27 minute wait, removes the 16.7% orphan rate, and removes the typo class entirely, because there is no invoice number for a teacher to mistype.

The five things that still need a human are the five that money cannot settle: a full batch, a half payment, a failed payment, a requested batch change, and a payer whose contact details do not match. Those are the exception paths, and they get owners, SLAs and drafted messages.
