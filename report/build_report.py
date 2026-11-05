import base64
import csv
import html
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "report"
CHARTS = OUT / "charts"
OUTPUTS = ROOT / "outputs"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { size: A4; margin: 14mm 15mm 13mm 15mm; }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 9.6pt; line-height: 1.44; color: #15191f; }
.page { page-break-after: always; }
.page:last-child { page-break-after: auto; }
h1 { font-size: 30pt; line-height: 1.06; letter-spacing: -0.6px; margin: 10px 0 12px; font-weight: 600; }
h2 { font-size: 14pt; line-height: 1.2; letter-spacing: -0.2px; margin: 2px 0 8px; font-weight: 600; }
h3 { font-size: 10.2pt; margin: 10px 0 3px; font-weight: 600; }
p { margin: 0 0 6px; }
.kicker { font-size: 7.6pt; letter-spacing: 1.3px; text-transform: uppercase; color: #66707d; font-weight: 600; }
.lede { font-size: 12pt; line-height: 1.38; color: #333b45; margin-bottom: 10px; }
.muted { color: #66707d; }
.small { font-size: 8.4pt; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 8pt; }
table { width: 100%; border-collapse: collapse; margin: 4px 0 8px; }
th { text-align: left; font-size: 7.4pt; letter-spacing: 0.5px; text-transform: uppercase; color: #66707d;
  border-bottom: 1px solid #cfd6de; padding: 3px 5px 4px 0; font-weight: 600; }
td { padding: 3.5px 5px 3.5px 0; border-bottom: 1px solid #e7ebef; vertical-align: top; font-size: 8.5pt; }
tr:last-child td { border-bottom: none; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; margin: 8px 0 10px; }
.kpi { border: 1px solid #e3e7ec; border-radius: 5px; padding: 7px 9px; }
.kpi b { display: block; font-size: 15pt; font-weight: 600; letter-spacing: -0.3px; line-height: 1.1; }
.kpi span { display: block; font-size: 8.2pt; margin-top: 2px; }
.kpi em { display: block; font-size: 7.6pt; color: #66707d; font-style: normal; margin-top: 1px; }
.kpi.leak b { color: #a33131; }
.kpi.good b { color: #1c7c54; }
figure { margin: 6px 0 8px; }
figure svg { width: 100%; height: auto; display: block; }
figcaption { font-size: 7.8pt; color: #66707d; margin-top: 3px; }
.note { background: #f6f7f9; border-left: 3px solid #1f5f8b; padding: 7px 9px; margin: 7px 0; font-size: 8.8pt; }
.note.leak { border-left-color: #a33131; }
.note.good { border-left-color: #1c7c54; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.msg { border: 1px solid #e3e7ec; border-radius: 5px; padding: 7px 9px; margin-bottom: 6px; background: #fbfcfd; }
.msg .head { font-size: 7.6pt; color: #66707d; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 3px; }
.msg p { margin: 0; font-size: 8.7pt; }
.cover { padding-top: 18mm; }
.cover h1 { margin-top: 14px; }
.thesis { border-left: 3px solid #1f5f8b; padding: 8px 12px; margin: 16px 0 14px; font-size: 11pt; line-height: 1.4; background: #f6f7f9; }
.cover-meta { font-size: 8.4pt; color: #66707d; margin-bottom: 18px; }
.contents { border-top: 1px solid #e3e7ec; padding-top: 8px; }
.contents div { display: flex; gap: 10px; padding: 3.5px 0; border-bottom: 1px solid #f0f2f5; font-size: 8.9pt; }
.contents span { width: 18px; color: #1f5f8b; font-weight: 600; }
ul { margin: 3px 0 7px 15px; padding: 0; }
li { margin-bottom: 2.5px; }
ol { margin: 3px 0 7px 15px; padding: 0; }
.pill { display: inline-block; padding: 1px 6px; border-radius: 9px; background: #eef1f4; font-size: 7.6pt;
  font-family: ui-monospace, Menlo, monospace; }
.risk-h { color: #a33131; font-weight: 600; }
"""


def esc(value):
    return html.escape(str(value))


def p(text, cls=""):
    return "<p class='{}'>{}</p>".format(cls, text)


def table(headers, rows, numeric=(), widths=None):
    head = "".join("<th class='num'>{}</th>".format(esc(h)) if i in numeric else "<th>{}</th>".format(esc(h)) for i, h in enumerate(headers))
    body = []
    for row in rows:
        cells = []
        for index, cell in enumerate(row):
            klass = " class='num'" if index in numeric else ""
            cells.append("<td{}>{}</td>".format(klass, esc(cell)))
        body.append("<tr>{}</tr>".format("".join(cells)))
    attrs = ""
    if widths:
        attrs = "<colgroup>{}</colgroup>".format("".join("<col style='width:{}'>".format(w) for w in widths))
    return "<table>{}<thead><tr>{}</tr></thead><tbody>{}</tbody></table>".format(attrs, head, "".join(body))


def kpi(value, label, note, tone=""):
    return "<div class='kpi {}'><b>{}</b><span>{}</span><em>{}</em></div>".format(tone, esc(value), esc(label), esc(note))


def chart(name, caption):
    svg = (CHARTS / name).read_text(encoding="utf-8")
    return "<figure>{}<figcaption>{}</figcaption></figure>".format(svg, esc(caption))


def png_uri(path):
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def money(value):
    return "INR {:,.0f}".format(float(value or 0))


def page(kicker, title, body):
    return "<section class='page'><div class='kicker'>{}</div><h2>{}</h2>{}</section>".format(esc(kicker), esc(title), body)


def build():
    summary = json.loads((OUTPUTS / "summary.json").read_text(encoding="utf-8"))
    savings = json.loads((OUTPUTS / "savings_model.json").read_text(encoding="utf-8"))
    metrics = summary["metrics"]
    auto_rows = read_csv(OUTPUTS / "auto_approved.csv")
    messages = read_csv(OUTPUTS / "messages.csv")
    invoice_rows = read_csv(OUTPUTS / "invoice_status.csv")
    exceptions = read_csv(OUTPUTS / "exceptions.csv")
    base = savings["base"]

    by_id = {row["message_id"]: row for row in messages}
    stuck = [row for row in invoice_rows if row["stuck_over_12h"] == "Yes"]

    cover = """
<section class='page cover'>
  <div class='kicker'>Bambinos.live &middot; AI Program Manager (Operations) &middot; Take-home case</div>
  <h1>Renewals that die<br>in the paperwork</h1>
  <p class='lede'>A leakage audit of the renewal to scheduling pipeline, a zero-touch workflow for clean renewals,
  a working reconciliation engine, and a rollout plan that does not put a live class at risk.</p>
  <div class='thesis'>Twelve parents paid. One child has a class on the calendar. The gap is not effort.
  It is a form that duplicates a payment record, and a step after approval that nobody owns.</div>
  <div class='cover-meta'>Prepared November 2026 &middot; data as of 3 November 2026, 18:00 &middot; 13 renewal cases,
  12 with money received &middot; 32 tests, 6 charts, 1 dashboard</div>
  <div class='contents'>
    <div><span>A</span>Executive summary and the leakage audit</div>
    <div><span>A</span>Every failure mode, counted, with the money attached</div>
    <div><span>B</span>Why each manual step exists, and which one to delete</div>
    <div><span>B</span>The redesigned flow, before and after</div>
    <div><span>B</span>Exception routing, owners, SLAs and escalation</div>
    <div><span>C</span>The eight metrics and their baselines</div>
    <div><span>C</span>The prototype: rules, thresholds, results, messages</div>
    <div><span>D</span>The ops head dashboard and the morning routine</div>
    <div><span>D</span>Time and cost model with editable assumptions</div>
    <div><span>D</span>SOPs, 30-60-90 rollout, rollback and live schedule safety</div>
    <div><span>D</span>Risks, limits, and what I would do differently</div>
  </div>
</section>
"""

    exec_body = "".join([
        "<div class='kpis'>",
        kpi("16.7%", "paid invoices with no teacher form", "2 of 12, INR 29,000", "leak"),
        kpi("91.7%", "paid renewals with no future class", "11 of 12, INR 126,850, proxy"),
        kpi("27.1 min", "median wait for a form", "n=10, worst 49.8"),
        kpi("75.0%", "paid renewals that need no human", "9 of 12, zero-touch eligible", "good"),
        kpi("144 h", "ops hours saved per month", "at 1,000 renewals, base case", "good"),
        kpi("4.3 mo", "payback on the build", "INR 2,00,000 one time"),
        "</div>",
        p("The pipeline is not slow because Ops is slow. In all four cases where a form arrived and Ops approved it, the "
          "approval and the booking request were created in the same minute. The delay sits upstream in a form that "
          "repeats information the payment already holds, and downstream in an allocation step that has no named owner."),
        p("On this data, 2 of 12 paid invoices never got a form at all. Another 8 of 12 forms were still unapproved at the "
          "snapshot, the oldest for 32.5 hours. Two of the four bookings never produced a session. The end state is "
          "11 paying students with no future class in the schedule export, worth INR 126,850 of the INR 138,850 collected."),
        p("The fix is to stop treating the teacher form as the trigger. For a same-batch renewal the invoice already "
          "carries the student, the class, the batch, the teacher, the amount and the discount. The only field the form "
          "adds is a preferred time, and in 11 of 12 forms that time is identical to the batch the child is already in. "
          "The form is not a control, it is a queue."),
        p("I built the engine that acts on that: 700 lines of Python, no runtime dependencies, 32 tests covering every "
          "reason code, an n8n export and a Google Sheets spec that mirror the logic, and three prompt files. It "
          "auto-approves 7 of 13 cases today and would clear 9 of 12 paid renewals with no human. The five blocking exceptions it "
          "leaves have an owner, an SLA and a drafted message."),
        p("That is worth about 144 ops hours a month at 1,000 renewals, INR 43,186, against a one-time build of about "
          "INR 2,00,000. The ask is small: three weeks in shadow mode, and one live-roster validation that confirms "
          "the same-batch renewal retains an existing seat."),
    ])
    pages = [cover, page("A · Executive summary", "The pipeline leaks in three places, and none of them is effort", exec_body)]

    join_rows = [
        ("1_invoices.csv", "13", "id", "Money received, gateway reference, payer contact"),
        ("2_faculty_form_unapproved.csv", "12", "id", "The teacher's claim about the same payment"),
        ("3_booking_requests.csv", "4", "id", "Ops approval, one row per approved form"),
        ("4_class_schedule_bookings.csv", "2", "id", "Actual sessions, the only proof a class exists"),
        ("reference_active_batches_and_students.csv", "13", "student_id", "Active batch, teacher, fee, capacity"),
    ]
    method_body = "".join([
        p("Five files, 44 rows. I read every row before writing a rule, because a rule built on an assumed schema is "
          "how you get a matcher that scores the wrong invoice at 0.97."),
        table(["File", "Rows", "Key", "What it is"], join_rows, numeric=(1,), widths=("34%", "8%", "10%", "48%")),
        p("Joins, ranked by how much I trust them. <b>student_id</b> is exact in 13 of 13 invoices and 12 of 12 forms. "
          "<b>invoice_id</b> is exact in 10 of 12 forms; one is a typo (84931 against a real 84913) and one is a duplicate "
          "submission. <b>faculty_form_id</b> links only 4 of 12 forms to a booking. <b>bookingrequest_id</b> reaches only "
          "one of four bookings. The invoice link is well formed in all 12 forms but must never be used as a key, because "
          "two invoice URLs differ by three characters out of fifty."),
        p("<b>form_submission_lag</b> is measurable for 10 forms, <b>approval_lag</b> for 4, and <b>payment to schedule</b> "
          "for exactly 1. I report the sample size next to every timing number, because a median of one is an anecdote."),
        "<div class='note leak'><b>What this data cannot settle.</b> All names, phones and emails are masked, so fuzzy "
        "name matching cannot be validated here. There are no term start or end dates, so class interruption is a proxy: "
        "money received and no future session row. There is no gateway settlement feed, so a late payment or a chargeback "
        "is invisible. And the schedule table has 2 rows for 12 paid renewals, which is either a catastrophe or a partial "
        "export. I treat it as partial and say so wherever the number appears.</div>",
        p("Three days of data, 13 cases, one Sunday to Tuesday window. Every monthly figure in this report is a scenario "
          "with the volume assumption written next to it, not a measurement."),
    ])
    pages.append(page("A · Method", "What is in the files, and what they cannot tell me", method_body))

    funnel_body = "".join([
        chart("funnel.svg", "Figure 1. The renewal funnel on 13 cases. Counts are exact; the final bar is a partial schedule export."),
        p("Thirteen invoices were raised. Twelve collected money. Eleven distinct invoices got a form. Four were approved. "
          "Four bookings were created. One student has session rows."),
        p("Each drop has a different cause, which matters because no single fix would have caught all of them. The two "
          "orphans needed no form at all: one is a GCC parent who paid INR 18,000, the other a chess parent who paid "
          "INR 11,000, and neither teacher submitted anything. The eight unapproved forms needed a decision that never "
          "came. The three unscheduled bookings exposed two allocation failures and one false batch-full rule."),
        p("The shape of the funnel is the argument for the redesign. The middle of the pipeline, where a human retypes a "
          "payment into a form and another human checks it, holds no information the system did not already have. It "
          "only adds waiting, and two ways to lose a child: the form never arrives, or the approval never happens."),
    ])
    pages.append(page("A · Leakage audit", "Where students get stuck, stage by stage", funnel_body))

    failure_rows = [
        ("Paid invoice, no teacher form", "2", "12 paid, 16.7%", "INR 29,000", "84906, 84910"),
        ("Approved, never scheduled", "2", "4 bookings, 50%", "INR 21,500", "5502 idle 51.7h, 5505 failed"),
        ("Form names a missing invoice", "1", "12 forms, 8.3%", "INR 11,500", "3313 points at 84931"),
        ("Invoice used in two forms", "1", "11 invoices, 9.1%", "double booking risk", "3308 and 3309, 5.2 min apart"),
        ("Claimed amount differs", "1", "12 forms, 8.3%", "INR 5,250", "3310 claims 10,500 against 5,250"),
        ("Part payment", "1", "13 invoices, 7.7%", "INR 5,250", "84909, installment 1 of 2"),
        ("Failed payment", "1", "13 invoices, 7.7%", "INR 12,000", "84911, no gateway payment id"),
        ("Payer contact mismatch", "1", "12 paid, 8.3%", "INR 12,000", "84904 paid from XXXX77, record has XXXX04"),
        ("Batch at capacity", "1", "12 forms, 8.3%", "INR 11,000", "9205 at 6 of 6"),
        ("Batch change", "1", "12 forms, 8.3%", "INR 9,000", "3312 wants Sat/Sun 11:00"),
        ("Student missing from reference", "0", "13 students", "0", "all present"),
        ("Malformed invoice URL", "0", "12 forms", "0", "all 12 well formed"),
        ("Duplicate schedule rows", "0", "2 rows", "0", "distinct dates"),
        ("Currency mismatch", "0", "12 paid", "unknown", "no currency field in the reference table"),
    ]
    failure_body = "".join([
        p("Every hypothesis in the brief, tested, with the denominator stated. The rows that came back zero stay in the "
          "table because a rule that fires on clean data is worse than no rule."),
        table(["Failure mode", "Count", "Denominator", "Value at risk", "Evidence"], failure_rows, numeric=(1,),
              widths=("28%", "8%", "16%", "14%", "34%")),
        "<h3>Five things the brief did not ask for</h3>",
        p("<b>The batch-full block is a counting artefact.</b> Batch 9205 is at 6 of 6 and student 68105 is one of "
          "those six. A same-batch renewal extends that occupied seat rather than taking a seventh, so the engine retains "
          "it automatically while keeping a hard capacity block for a genuinely new allocation."),
        p("<b>Approval is not the bottleneck.</b> All four approved forms produced a booking in the same minute. Then "
          "booking 5502 sat at Pending_Batch_Allocation for 51.7 hours. A faster approval inbox would move the wrong number."),
        p("<b>A discount looks like an underpayment.</b> Form 3307 claims 7,600 against a 9,500 list price. The invoice "
          "records a 1,900 discount, exactly 20%, so the claim matches the net amount. Any rule that compares the form to "
          "the gross price flags every scholarship renewal."),
        p("<b>The form is not independent evidence.</b> On 84904 the invoice carries a number that appears nowhere else, "
          "and the form supplies the one that matches the parent record. The teacher typed it from the same WhatsApp "
          "thread that produced the payment, so it is a copy of the conversation, not a second source."),
        p("<b>Cross-border money is unreconciled.</b> Two Stripe payments, from a UAE and a US number, both billed in INR "
          "for INR 40,000 combined. There is no currency field in the reference table, so nothing in this data can confirm "
          "the settlement amount."),
    ])
    pages.append(page("A · Failure modes", "Fourteen hypotheses, counted, with the money attached", failure_body))

    step_rows = [
        ("Invoice created by the gateway", "Record that the parent paid", "Holds. It is the only source of truth for money.", "Keep, and promote to the trigger for the whole flow."),
        ("Teacher fills a renewal form", "Capture student, batch, amount, preferred time", "Four of five fields are already on the invoice. The fifth matches the current batch in 11 of 12 forms.", "Remove as a trigger. Keep as corroboration and as the carrier of a batch-change request."),
        ("Ops approves the form", "Verify the payment before booking", "Verification is three field comparisons. Approval and booking creation landed in the same minute in all four cases.", "Replace with rules. Humans keep capacity, identity and policy decisions."),
        ("Batch allocated, sessions created", "Parent or Ops picks days and time", "For a same-batch renewal there is nothing to pick. Booking 5502 waited 51.7 hours for a click.", "Auto-allocate same-batch. Escalate only batch changes."),
    ]
    form_body = "".join([
        p("The brief asks whether the teacher form can be eliminated for clean renewals. The answer is arithmetic, not "
          "opinion. Take the four fields the form exists to capture and ask where else they live."),
        table(["Step", "Stated purpose", "Does it hold", "Decision"], step_rows, widths=("22%", "18%", "34%", "26%")),
        chart("timing.svg", "Figure 2. Where the 105 minutes went on the one case that completed. Approval was 43% of it."),
        p("The only field the form genuinely adds is the preferred day and time. In 11 of 12 forms it is identical to the "
          "batch the student is already in, because the parent is renewing the same slot with the same teacher. The "
          "twelfth is a real batch change, and that is the one case where a form is still worth collecting."),
        p("So the redesign does not delete the form. It demotes it. The invoice triggers the flow, the form becomes a piece "
          "of evidence that can block an edge case but never gates a clean one, and the queue that produced 27 minutes of "
          "median waiting and a 16.7% orphan rate stops existing."),
    ])
    pages.append(page("B · Process audit", "Why each manual step exists, and which one to delete", form_body))

    flow_body = "".join([
        chart("flow_before.svg", "Figure 3. Today. Three handoffs, three different ways to lose a paying child."),
        chart("flow_after.svg", "Figure 4. After. One trigger, two lanes, and a form that no longer gates anything."),
        p("The fast lane is deliberately narrow. All four conditions must hold: the invoice is Paid or Partially_Paid "
          "with the net equal to billed minus discount; the student, at least one contact channel, the teacher and the "
          "class match the active record; and the renewal is same-batch and the form, when present, names that batch. "
          "That continuation retains its existing seat. Any new allocation must reserve capacity; if it cannot, the case "
          "goes to the exception lane. It never half-approves."),
        p("In the exception lane the case keeps everything the fast lane would have given it: the resolved invoice, the "
          "batch, the amount, the payer, and a sentence explaining exactly which check failed. What changes is that a "
          "named person now owns it, with a clock running."),
    ])
    pages.append(page("B · Re-engineered workflow", "One trigger, two lanes, no form in the critical path", flow_body))

    routing_rows = [
        ("Batch at capacity", "R08", "ops_agent", "4h / 8h", "Ask the teacher whether the batch continues. If yes, renew in place. If no, offer a batch with a free seat."),
        ("Part payment", "R06", "finance", "4h / 24h", "Agree a balance date or pro-rate the sessions. Do not release 24 sessions on half the fee."),
        ("Payer contact mismatch", "R12", "ops_agent", "4h / 4h", "One call to confirm the payer, then release. The parent also gets a message so the wait is explained."),
        ("Batch change", "R09", "parent", "8h / 24h", "Confirm days, time and teacher, then allocate. The only case where the form is still the trigger."),
        ("Payment not completed", "R07", "parent", "24h / 48h", "Send the retry link, hold the class, trace the reference if money left the account."),
    ]
    ladder_rows = [
        ("1", "Assigned owner", "Case enters the queue", "Resolve within policy"),
        ("2", "ops_lead", "SLA breached or value above INR 15,000", "Reassign, approve a seat override with teacher consent"),
        ("3", "Head of Operations", "Breach over 24h, or any child misses a class", "Approve refunds, credits, batch creation"),
        ("4", "Finance lead", "Payment dispute or chargeback", "Owns gateway reconciliation"),
    ]
    routing_body = "".join([
        p("Each exception type goes to the person who can actually change its state. A teacher cannot see capacity, so a "
          "teacher never owns a capacity decision. Finance cannot call a parent about a class, so finance owns the money "
          "question and Ops owns the message."),
        table(["Situation", "Code", "Owner", "Reply / resolve", "First action"], routing_rows,
              widths=("22%", "7%", "11%", "13%", "47%")),
        "<h3>The escalation ladder is a clock, not a judgement call</h3>",
        table(["Level", "Role", "Trigger", "Authority"], ladder_rows, widths=("7%", "20%", "34%", "39%")),
        "<h3>What the parent actually receives</h3>",
        "<div class='msg'><div class='head'>WhatsApp to parent &middot; R12 &middot; draft from outputs/messages.csv</div>"
        "<p>Hi, this is Priya from Bambinos. An***a Iy***r's renewal of Rs 12,000 came through on 2 Nov. The payment shows "
        "+91-9844XXXX77, which is not the number we have on file, so I want to confirm it is yours before I release the "
        "classes. Is that the right number? Reply yes and I'll get the classes scheduled today.</p></div>",
        p("Three sentences, one specific number, no blame, and a promise the ops agent can keep. The full draft set is 12 "
          "messages across 5 cases, in <span class='mono'>outputs/messages.md</span>."),
    ])
    pages.append(page("B · Exception handling", "Every failure has one owner and a clock", routing_body))

    metric_rows = [
        ("Orphaned Invoice Rate", "16.7% (2 of 12)", "under 2%", "ops_agent"),
        ("Payment to Schedule", "1.75h, n=1; 11 of 12 open", "median under 15 min, p90 under 4h", "ops_agent"),
        ("Form Submission Lag", "27.1 min median, n=10", "not applicable once the form is optional", "teacher"),
        ("Approval Lag", "1.54h median, n=4; 8 of 12 unapproved", "under 5 min auto, 4h exception", "ops_agent"),
        ("Unscheduled Booking Rate", "75% (3 of 4)", "under 5% at 24h", "ops_agent"),
        ("First Pass Auto-Approval Rate", "0%", "70%", "Head of Ops"),
        ("Exception Resolution Time", "8.0h median open age, n=5", "median 4h, p90 24h", "assigned owner"),
        ("Class Interruption Rate", "91.7% (11 of 12), proxy", "under 2%", "Head of Ops"),
    ]
    metrics_body = "".join([
        p("Eight metrics, each with a formula an ops lead can recompute from the same files. Baselines come from this "
          "dataset at 2026-11-03 18:00. Where the sample is too small to be a baseline, I say so rather than quoting it "
          "as one."),
        table(["Metric", "Baseline today", "Target", "Owner"], metric_rows, widths=("30%", "30%", "26%", "14%")),
        p("The one that matters is the last. Every other metric is a leading indicator; class interruption is the thing "
          "the parent experiences. It is also the number I trust least, because the schedule export has two rows. If a "
          "full export shows the same rate, this stops being a process problem and becomes an emergency."),
        "<div class='note'><b>Deliberately not an SLA.</b> Teacher response time, because teachers are paid per class and "
        "policing their admin would need a contract change. Parent response time, because a parent who paid and stopped "
        "replying is not a process failure. Time to first class, because it depends on the batch calendar, not on Ops.</div>",
        p("Escalation is automatic at the SLA. The engine stamps <span class='mono'>sla_hours</span> on every row, the "
          "dashboard counts down against it, and the daily digest names whatever is past due. Nobody has to decide whether "
          "a case is late."),
    ])
    pages.append(page("C · Metrics and SLAs", "Eight numbers, and the one that actually matters", metrics_body))

    proto_body = "".join([
        p("Five CSVs in, six operational artifacts out, one command. The pipeline is load, normalize, match, decide, allocate seats, "
          "write. No runtime dependencies, no network calls, no wall clock in the outputs."),
        "<h3>The rule order, which is also the blast radius</h3>",
        "<ol><li>Resolve the invoice: exact id, then link, then fuzzy repair with a uniqueness requirement.</li>"
        "<li>Payment settled: status must be Paid or Partially_Paid.</li>"
        "<li>Fee settled: net must equal billed minus discount, within tolerance.</li>"
        "<li>Claim matches: the form amount must equal the net collected.</li>"
        "<li>Identity: student id, then at least one contact channel.</li>"
        "<li>Batch: same-batch, active, correct teacher and class, valid session count.</li>"
        "<li>Seats: same-batch renewals retain an existing seat; new allocations reserve one through a ledger.</li>"
        "<li>State: already scheduled, approved but unscheduled, or approved with no booking.</li></ol>",
        table(["Parameter", "Value", "Why that value"], [
            ("Invoice similarity floor", "0.72", "84931 to 84913 scores 0.80; unrelated numbers score near 0"),
            ("Runner-up margin", "0.05", "refuse when two candidates are close, rather than guessing"),
            ("Amount tolerance", "INR 1 or 0.5%", "gateway rounding, nothing more"),
            ("Stuck invoice threshold", "12 hours", "the dashboard tile the ops head asked for"),
            ("Escalation clock", "24 hours", "one business day"),
        ], widths=("30%", "18%", "52%")),
        p("<b>What it refuses to do.</b> It will not approve against a failed payment, even with a screenshot. It will not "
          "pick between two plausible invoices; it returns R02 and asks a teacher for the number. It will not edit an "
          "invoice amount to match a form. And it will not put a second booking on an invoice that already has one."),
        p("Every row carries a reason code and a sentence with the numbers in it. That is the difference between a script "
          "and something an ops team can trust at 9am on a Monday."),
    ])
    pages.append(page("C · Prototype", "Deterministic rules, with the LLM kept on a short leash", proto_body))

    auto_table_rows = [
        (row["case_key"], row["evidence"], row["classbatch_id"], row["seats_left_after"], row["flags"] or "-")
        for row in auto_rows
    ]
    reason_rows = [(item["code"], item["label"], item["count"], item["owner"]) for item in summary["exceptions_by_reason"]]
    results_body = "".join([
        p("Seven cases auto-approved, five blocked, one duplicate closed, one already scheduled. The seven rows in "
          "<span class='mono'>auto_approved.csv</span> are ready to become bookings: five came from a form, two from an "
          "invoice with no form at all, and one from a repaired reference."),
        table(["Case", "Evidence", "Batch", "Seats left", "Flags"], auto_table_rows, numeric=(3,),
              widths=("10%", "18%", "12%", "12%", "48%")),
        table(["Code", "Exception", "Count", "Owner"], reason_rows, numeric=(2,), widths=("10%", "56%", "10%", "24%")),
        p("<b>The decision I would defend hardest is a refusal.</b> Case 84904 was paid from +91-9844XXXX77, which matches "
          "neither the registered mobile (+91-9844XXXX04) nor the registered email. The teacher's form supplies the 04 "
          "number, and the remark says the mother paid. I still held it, for one call. Auto-approving would have saved two "
          "minutes and risked a misapplied payment on a child whose parent would then have to argue about it."),
        p("Case 84913 shows the opposite. The form typed invoice 84931 and the real invoice is 84913. The matcher repaired "
          "it because the student, the amount and the teacher all matched and there was exactly one candidate. That is a "
          "class cleared in milliseconds that a human would have bounced back to the teacher."),
        p("Two of the seven auto approvals exist only because the form was demoted. Their teachers never submitted "
          "anything, and the payment alone was enough: " + money(metrics["orphaned_value_inr"]) + " that the current "
          "process would still be chasing."),
    ])
    pages.append(page("C · Prototype results", "Eight rows cleared, five blocking exceptions, one refusal I would defend", results_body))

    def message_block(message_id, label):
        row = by_id.get(message_id)
        if not row:
            return ""
        return ("<div class='msg'><div class='head'>{} &middot; {} to {}</div><p>{}</p></div>"
                .format(esc(label), esc(row["channel"]), esc(row["audience"]), esc(row["message"])))

    message_body = "".join([
        p("Twelve drafts across five cases, each addressed to one person, each containing the number that triggered it. "
          "These are the exact strings in <span class='mono'>outputs/messages.csv</span>, produced by templates with no "
          "API key."),
        message_block("MSG-84904-R12-parent", "Payer mismatch, to the parent"),
        message_block("MSG-84909-R06-finance", "Part payment, to finance"),
        message_block("MSG-84912-R09-parent", "Batch change, to the parent"),
        message_block("MSG-84911-R07-parent", "Failed payment, to the parent"),
        p("<b>Where the LLM sits.</b> Three prompts in <span class='mono'>prompts/</span>. One polishes message copy, one "
          "resolves genuinely ambiguous invoice references, one triages an exception that the rule set has not seen before. "
          "All three take a facts payload and are forbidden from adding a number, a date or a promise. The default run does "
          "not call any of them, and the output is identical without a key."),
        p("That is a deliberate cost decision as much as a safety one. Message drafting is the only place where wording "
          "quality matters and a wrong answer is cheap. Decisions are not."),
    ])
    pages.append(page("C · Drafted messages", "Short, specific, and addressed to one person", message_body))

    dash_path = ROOT / "dashboard" / "screenshots" / "dashboard.png"
    shot = ("<figure><img src='{}' alt='Ops dashboard' style='width:100%;border:1px solid #e3e7ec;border-radius:4px'>"
            "<figcaption>Figure 5. The dashboard, built from the engine outputs, not mocked up.</figcaption></figure>"
            .format(png_uri(dash_path))) if dash_path.exists() else "<div class='note leak'>Dashboard screenshot missing.</div>"

    tiles_rows = [
        ("Stuck invoices over 12h", "Money received, no session row, older than 12 hours", str(metrics["stuck_invoices_over_12h"])),
        ("Blocking exceptions", "Rows where a human must change state before a class exists", str(summary["exceptions_blocking"])),
        ("Unscheduled bookings", "Bookings with zero session rows", "3 of 4"),
        ("Auto approval rate", "Cases pushed with no human edit, over all cases", "{:.0f}%".format(summary["auto_approval_rate"] * 100)),
        ("Hours saved", "Monthly ops hours avoided at the modelled volume", "{:.0f}".format(summary["estimated_hours_saved_per_month"])),
        ("Collected with no class", "Net revenue on invoices with no future session", money(metrics["revenue_without_class_inr"])),
    ]
    dashboard_body = "".join([
        shot,
        table(["Tile", "Definition", "Today"], tiles_rows, widths=("24%", "62%", "14%")),
        p("The morning routine is twenty minutes, not a dashboard tour. Read the six tiles, then clear your own exceptions "
          "oldest first, because the oldest is a parent who has waited longest. Then spot-check five auto-approved rows, "
          "flagged ones first. If one is wrong, stop the engine before fixing it by hand."),
        p("The tile I would watch is not the exception count. It is the age of the oldest open exception. A stable count "
          "with a rising age means the queue is being triaged but not cleared, which is exactly how the current process "
          "fails: 8 forms pending, none of them moving."),
    ])
    pages.append(page("D · Ops dashboard", "What the Head of Operations sees at 9am", dashboard_body))

    assumption_rows = [
        ("Monthly renewal volume", "1,000", "Scenario. The file shows 13 cases over 3 days"),
        ("Ops loaded hourly cost", "INR 300", "About INR 54,000 a month at 174 productive hours"),
        ("Context switching allowance", "25%", "Task switching and re-reading threads, added to manual time"),
        ("Automation overhead", "10%", "Digest review and the 5% audit sample"),
        ("Auto approval rate", "70%", "Observed 75.0% on this data, modelled lower for sample noise"),
        ("One time build", "INR 2,00,000", "Six weeks of one engineer plus part of an ops lead"),
    ]
    sensitivity_rows = [
        ("55%", "{:.0f}".format(savings["scenarios"]["low"]["hours_saved_per_month"]), money(savings["scenarios"]["low"]["cost_saved_per_month_inr"]), "{} mo".format(savings["scenarios"]["low"]["payback_months"])),
        ("70%", "{:.0f}".format(base["hours_saved_per_month"]), money(base["cost_saved_per_month_inr"]), "{} mo".format(base["payback_months"])),
        ("80%", "{:.0f}".format(savings["scenarios"]["high"]["hours_saved_per_month"]), money(savings["scenarios"]["high"]["cost_saved_per_month_inr"]), "{} mo".format(savings["scenarios"]["high"]["payback_months"])),
    ]
    savings_body = "".join([
        chart("savings.svg", "Figure 6. Ops hours per month at 1,000 renewals. Today is 162.7 hours; the base case is 18.7."),
        table(["Assumption", "Value", "Why"], assumption_rows, widths=("28%", "16%", "56%")),
        table(["Auto approval rate", "Hours saved / month", "Cost saved / month", "Payback"], sensitivity_rows,
              numeric=(1, 2, 3), widths=("22%", "24%", "30%", "24%")),
        p("Today the same 1,000 renewals cost 162.7 ops hours: 7.81 minutes of task time per case, inflated by a 25% "
          "context-switch allowance. The redesign lands at 18.7 hours, because 70% of cases need a quarter of a minute "
          "of oversight and the remaining 30% need 3.1 minutes each."),
        p("<b>What is not in the number.</b> Recovered revenue. If faster scheduling stopped even 2% of at-risk renewals "
          "from lapsing, that would add roughly INR 2.8 lakh a month at this average net, which dwarfs the labour saving. "
          "I left it out because the churn rate is invented and the labour saving is not."),
        "<div class='note good'>Every input sits in <span class='mono'>engine/savings_assumptions.json</span>. Change the "
        "volume to 300 and the hours scale linearly; the payback moves to 14 months. Nothing in the model is hidden.</div>",
    ])
    pages.append(page("D · Savings model", "144 hours a month, with every assumption visible", savings_body))

    rollout_rows = [
        ("Days 0 to 30", "Shadow mode. Engine recommends, Ops decides. Every disagreement logged with one line of why.", "Zero disagreements on the last 50 cases of a code before it can go live."),
        ("Days 31 to 60", "Pilot with two teachers and about 20% of volume. Only R00 and R17 write.", "No wrong child scheduled, auto-approval rate within 10 points of prediction."),
        ("Days 61 to 90", "Phased cutover by reason code. Ops keeps the exception lane.", "Median exception age under 4 hours for two consecutive weeks."),
    ]
    policy_body = "".join([
        p("<b>Teachers.</b> The SOP is five things they may be asked, four rules that save them time, and a list of what "
          "we will never ask them to do, including chase a parent for money. The headline for them is that the form is "
          "gone for same-batch renewals, so this rollout removes admin rather than adding it. That is the whole adoption "
          "argument."),
        p("<b>Ops.</b> The SOP replaces the approval inbox with an exception queue. Work oldest first, close on state "
          "change rather than on reply, and never edit an invoice amount to match a form. The weekly review is 30 minutes "
          "on cases that took more than 24 hours, because three weeks of that list tells you which rule to change next."),
        table(["Window", "Focus", "Gate to pass"], rollout_rows, widths=("14%", "50%", "36%")),
        "<h3>Keeping live schedules safe</h3>",
        p("The engine never edits an existing session row. It writes bookings through one endpoint, and only for invoices "
          "with no existing booking. Before any write it produces the same rows in shadow mode so the diff can be read. "
          "Rollback is one switch that returns writes to manual while the engine keeps recommending, so a rollback cannot "
          "orphan a class that already exists."),
        p("<b>Rollback criteria, written before launch.</b> More than 0.5% false approvals in the audit sample. Any case "
          "where the wrong child is scheduled. More than two escalations a day caused by the engine rather than by the "
          "parent. Any breach of the 12 hour stuck threshold that the engine created rather than inherited."),
        p("The pilot is two teachers, not two hundred, because the failure modes I care about are social: a teacher who "
          "keeps filling forms out of habit, an ops agent who overrides without a reason. Both show up in week one with "
          "two teachers and are invisible at scale."),
    ])
    pages.append(page("D · Rollout", "SOPs, 30-60-90, and how a rollback cannot break a class", policy_body))

    risk_rows = [
        ("Wrong child scheduled", "Low", "High", "Hold on dual contact mismatch, 5% audit sample, refusal by default when two invoices fit"),
        ("False batch-full block", "Low", "Medium", "Retain the active student's seat; require a capacity reservation only for a new allocation"),
        ("Teacher resistance", "Medium", "Medium", "The form is removed, not added. No new admin for teachers"),
        ("Schedule export incomplete", "High", "High", "Verify in week one. Do not publish the interruption rate until it is real"),
        ("Volume breaks the Sheets version", "Medium", "Medium", "Move to Postgres and a queue. The rules are stateless and linear"),
        ("Overrides drift", "Medium", "Medium", "Override reason required, reviewed weekly, counted on the dashboard"),
    ]
    closing_body = "".join([
        table(["Risk", "Likelihood", "Impact", "Mitigation"], risk_rows, widths=("24%", "12%", "10%", "54%")),
        "<h3>What I would do differently</h3>",
        p("I would start from the schedule table, not the invoices. The funnel looks like an approval problem until you "
          "notice that approval and booking creation happen in the same minute, and the real gap is allocation. Reading "
          "the last table first would have found that in ten minutes instead of an hour."),
        p("I would also instrument time-in-state from day one. Every number in this report is reconstructed from "
          "timestamps that happen to exist, and two of the eight metrics have a sample size small enough that I have to "
          "apologise for them. A single <span class='mono'>state_changed_at</span> column would make all eight measurable."),
        p("And I would ask for one unmasked sample of 50 rows. The masked data is honest about structure and useless for "
          "validating the one thing that needs it, which is whether two names that look alike belong to the same child."),
        "<h3>What I am not claiming</h3>",
        p("This is a 13 case sample, not a production baseline. The interruption rate rests on a two row schedule table. "
          "The LLM path has never run against a real key. The n8n export is structurally valid and its JavaScript passes a "
          "syntax check, but it has not been imported into a live instance. The Sheets spec has not been pasted into a sheet."),
        p("What I am claiming is narrower and, I think, more useful: on the data provided, three quarters of paid renewals need "
          "no human, the five that do have a name and a clock, and every decision the machine makes can be read and argued "
          "with by the person who owns the class."),
    ])
    pages.append(page("D · Risks and limits", "What breaks, what I would do differently, what I am not claiming", closing_body))

    document = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>Renewals that die in the paperwork</title>"
        "<style>{}</style></head><body>{}</body></html>".format(CSS, "".join(pages))
    )
    target = OUT / "report.html"
    target.write_text(document, encoding="utf-8")
    return target


def to_pdf(html_path):
    pdf = OUT / "report.pdf"
    command = [
        CHROME,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--virtual-time-budget=5000",
        "--print-to-pdf={}".format(pdf),
        html_path.resolve().as_uri(),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if not pdf.exists():
        raise SystemExit("chrome failed: {}\n{}".format(result.returncode, result.stderr[-800:]))
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    pages = 0
    for line in info.splitlines():
        if line.startswith("Pages:"):
            pages = int(line.split(":")[1].strip())
    print("pdf {} pages, {} bytes".format(pages, pdf.stat().st_size))
    if pages < 12 or pages > 16:
        print("WARNING: page count outside the 12 to 16 target")
        return 1
    return 0


def main():
    html_path = build()
    print("wrote {}".format(html_path))
    return to_pdf(html_path)


if __name__ == "__main__":
    sys.exit(main())
