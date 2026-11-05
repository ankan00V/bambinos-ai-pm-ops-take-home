# Cheat sheet for the live review

## Six numbers to know cold

| Number | What it is |
| --- | --- |
| 13 cases, 12 with money | The dataset. 11 Paid, 1 Partially_Paid, 1 Failed |
| 16.7% | Paid invoices with no teacher form, 2 of 12, INR 29,000 |
| 75.0% | Paid renewals that can clear with no human, 9 of 12 |
| 53.8% | Auto-approved in this snapshot, 7 of 13, because 5 genuinely need a person |
| 91.7% | Paid renewals with no future class, 11 of 12, INR 126,850. Proxy, verify before quoting |
| 144 hours | Ops time saved per month at 1,000 renewals, base case |

## The one paragraph version

The payment gateway already knows the student, the class, the batch, the teacher, the amount and the discount. For 11 of 12 forms, the only extra field is a preferred time, and it matches the batch the child is already in. So the teacher form is not a control, it is a delay: 27 minutes of median waiting, 16.7% of paid invoices never getting one, and a typo class that exists only because a human retypes an invoice number. The engine reads the invoice, checks it against the active record, retains an existing seat for same-batch renewals, and routes the five true exception types to named owners with SLAs and drafted messages.

## Ten questions they will ask

**1. Your auto-approval rate is 54%. Why is that lower than the 75% zero-touch figure?**

Because the snapshot has 13 cases and 5 of them need a person: a failed payment, a half payment, a payer mismatch, a batch change, and one case stuck after approval. The apparent full-batch case is a same-batch renewal for a student already counted in the 6 of 6, so the engine retains the existing seat rather than treating it as a seventh student. The forward-looking number is 75.0%, which counts cases that would clear from a clean state. I report both because the first is what happened today and the second is what the design delivers.

**2. What stops a teacher submitting wrong information?**

Nothing, and that is the point. The form is no longer the trigger for a same-batch renewal, so a wrong form cannot block a child or move money. When a form disagrees with the invoice, the invoice wins and the form becomes a flag. The only place the form still matters is a batch change, where it carries the parent's request.

**3. How do you know the payment belongs to that child?**

Three signals: the `student_id` on the invoice, the payer contact against the registered contact, and the amount against the fee. If both contacts fail, the case is held for one call, which is what happens to 84904. If the student id itself disagrees with the form, it blocks outright. I do not treat a teacher-typed phone number as independent evidence, because it comes from the same WhatsApp thread as the payment.

**4. What happens if you run it twice?**

Nothing. No wall clock in the outputs, deterministic ordering, and a state check that skips any case with existing session rows. There is a test that runs the engine twice and compares file bytes. The other half of idempotency is refusing to write a second booking for an invoice that already has one.

**5. Is 91.7% class interruption real? That seems impossible.**

It is a proxy and I label it as one. The schedule table has two rows for twelve paid renewals. Either eleven children genuinely have no class, which would be the biggest fire in the company, or the export is partial. The arithmetic points at a partial export, because booking 5502 was approved and still shows as pending allocation 51.7 hours later. I would not quote this number externally until it is re-run on a full schedule export.

**6. Why not let an LLM make the decisions?**

Because I cannot explain a wrong answer to a parent. Every decision here is a rule with a reason code and a sentence containing the numbers. The LLM rewrites message copy only, and the system produces identical output without a key. It also costs nothing per case in the default path.

**7. What do you do when the batch is full?**

For a new allocation, the engine stops and routes to Ops; it never silently overflows a batch. On 9205, the renewal is for a student already inside the 6 of 6, so this is not a new allocation: the engine retains the existing seat. The test suite covers both that protection and the true full-batch block for a new allocation.

**8. Why is the discounted renewal not an exception?**

Because the form claimed 7,600 and the invoice net was 7,600. The 9,500 is the list price, and the invoice records a 1,900 discount, exactly 20%. A rule that compares claims to gross would flag every scholarship renewal. The engine compares to net and flags the discount separately as informational.

**9. What breaks first at ten times the volume?**

The Google Sheets version, on API limits and on the seat ledger, which needs row-level locking. The Python engine is stateless and linear, so the first real constraint is the booking API. The fix is a queue and Postgres, not a rewrite of the rules.

**10. How do you roll this out without breaking live classes?**

Shadow mode for three weeks: the engine writes recommendations, not bookings, and Ops logs every disagreement. A code goes live only when its last 50 disagreements are zero. Then a pilot with two teachers, then phased cutover by reason code. Rollback is one switch that returns writes to manual while the engine keeps recommending. Live schedules are never touched by the engine except through the booking endpoint, so a rollback cannot orphan an existing class.

## Three things to say if the room goes quiet

- The cheapest win in the dataset is one policy conversation: a renewing student in a full batch is already occupying a seat, so blocking them is probably wrong.
- The bottleneck is not approval. Approval and booking creation happen in the same minute. The wait is in allocation, where a booking sat for 51.7 hours.
- I would rather ship four rules that an ops person can audit than twenty that need a data scientist.

## What I would do in the first week if hired

Pull a full schedule export and recompute the interruption rate. That single number decides whether this is a process cleanup or an emergency.
