# Loom walkthrough script

Target length: 2 minutes 40 seconds. Screen recording, one take is fine. Keep the mouse moving and do not read the slides.

## 0:00 to 0:20, what this is

Show the cover and executive-summary page of `report/report.pdf`.

"This is a reconciliation engine for the renewal pipeline. It reads the four tables, decides which paid renewals can be scheduled without a human, and writes the auto-approved rows, the exceptions, and the messages. The thing to notice is what it does with the teacher form."

## 0:20 to 0:50, the finding

Stay on the executive-summary page; point to the orphaned-invoice and zero-touch KPI tiles.

"Twelve paid renewals. Two of them never got a form at all, which is sixteen point seven percent and twenty nine thousand rupees. For the other ten, the form adds a preferred time that is already identical to the batch the child is sitting in. So the form is not a control, it is a queue. Median wait was twenty seven minutes, and eight of twelve were still unapproved at the snapshot."

## 0:50 to 1:20, run it

Show the terminal.

"One command. No install, standard library only."

Run `python3 engine/run.py`.

"Thirteen cases. Seven auto-approved, five blocked, one duplicate closed, one already scheduled. Zero-touch eligible is seventy five percent of paid invoices. It also prints the leak numbers and the savings model."

## 1:20 to 1:50, the auto-approved file

Open `outputs/auto_approved.csv`.

"Seven rows waiting to become bookings. Five came from forms, two came from invoices with no form at all, and one had a mistyped invoice number that the matcher repaired. Every row has the batch, its explicit capacity action, and a sentence explaining why it passed."

Point at 84913.

"That one claimed invoice 84931. The real invoice is 84913. It repaired it because the student, the amount and the teacher all matched, and there was exactly one candidate."

Point at 84905 and its `retain_existing_seat` capacity action.

"This is the guardrail I care about most. The batch says six of six, but this child is already one of those six. A same-batch renewal retains an occupied seat; it does not create a seventh student. A genuine new allocation still blocks at capacity."

## 1:50 to 2:20, the exceptions and messages

Open `outputs/exceptions.csv`, then `outputs/messages.md`.

"Five blocking exceptions. Each has an owner, an SLA, hours open, and the specific number that caused it. This payer-mismatch case is held because the payment contact matches neither contact on the active student record."

Switch to messages.

"There are twelve drafted messages across five cases. This is the parent whose payment came from a different number. One call confirms it and the class is released. The drafts are templates by default, so the whole thing runs with no API key."

## 2:20 to 2:40, the dashboard and the ask

Open the dashboard.

"This is the morning view: stuck invoices over twelve hours, exceptions by owner, unscheduled bookings, and hours saved. The one number I would verify before trusting is the interruption rate, because the schedule table in this extract only has two rows. That is the first thing I would pull in week one."

## Delivery notes

- Do not apologise for the dataset size. Say "thirteen cases, here is what they show" and move on.
- If the recording runs long, cut the savings section, not the auto-approved file. The file is the proof.
- Say "sixteen point seven percent" out loud, not "16.7". Spoken decimals sound like reading.
