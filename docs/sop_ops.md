# SOP for the Ops team

This is the daily routine for the 10 person Ops team once the reconciliation engine is live. It replaces the manual approval inbox.

## The one rule

You do not approve clean renewals. The engine does that and writes them to `outputs/auto_approved.csv`, which is the queue that feeds `class_schedule_bookings`. Your job is the exception queue, plus a small daily audit of what the engine approved.

If you find yourself checking a payment against a form for a same-batch renewal, something has gone wrong. Stop and tell the ops lead.

## Morning routine, 20 minutes

1. Open the dashboard. Read five numbers: stuck invoices over 12 hours, blocking exceptions by owner, unscheduled bookings, yesterday's auto-approval rate, and anything past its SLA.
2. Clear your own exceptions oldest first, not newest first. Oldest is a parent who has been waiting longest.
3. Check the "past SLA" list. Anything there gets a message to the owner and, if it is over 24 hours, a note to the Head of Ops.
4. Spot-check 5 auto-approved rows. Pick the ones with flags on them first, then a random sample. Confirm the batch and the amount. If one is wrong, stop the engine before fixing it by hand.

## During the day

Exceptions arrive with an owner already assigned. Work them in this order.

| Priority | What it looks like | What you do |
| --- | --- | --- |
| P1 | Money received, no class, over 12 hours | Fix the seat or call the parent today. This is the only category that justifies interrupting someone |
| P2 | Money received, class within 24 hours | Fix before the next class |
| P3 | Money not received | Send the retry link, then leave it alone for 48 hours |
| P4 | Data mismatch with no money at risk | Fix when the queue is clear |

Every exception has a drafted message in `outputs/messages.md`. Send it, edit it if you know something the engine does not, but do not rewrite it from scratch. The drafts carry the specific number that triggered the flag, and that number is what makes the message land.

## Closing a case

A case is closed when the state changes, not when you have replied. That means one of:

- A booking exists and has schedule rows.
- The parent has explicitly chosen a new batch and it is allocated.
- Finance has confirmed the amount and released or held the sessions.
- The case is cancelled with a reason recorded.

Replying to a parent does not close a case. If you cannot change the state today, leave it open with a note and a next action date.

## Weekly, 30 minutes

1. Review every exception that took longer than 24 hours. Write one line on why. Three weeks of that list tells you which rule to change next.
2. Review all R12 payer mismatches. If the same parent keeps paying from a different number, fix the parent record instead of flagging it every term.
3. Review discounts. Any discount without an approval reference is a finance exception, not an ops one.
4. Pull the auto-approval rate and the false-positive count. If the rate drops, find out which rule started firing.

## What you must never do

- Approve a renewal against a failed payment because the parent sent a screenshot. The gateway is the only source of truth for whether money arrived.
- Schedule a child into a batch that is full without the teacher's explicit confirmation in writing. That is how a class gets interrupted later.
- Edit an invoice amount to make it match a form. Fix the form or the payment, never the ledger.
- Delete a duplicate form row. Close it with a reason so the next person can see what happened.
- Turn off the engine during a busy day. If it is producing bad rows, switch it to shadow mode, which stops the writes but keeps the recommendations.

## Shadow mode

For the first three weeks the engine runs in shadow. It writes recommendations, not bookings. Your job then is to compare its decision with what you would have done, and log every disagreement in the shared sheet with one line of why.

The engine goes live for a case type only when the last 50 disagreements for that type are zero.
