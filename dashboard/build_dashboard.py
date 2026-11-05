import csv
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"
TARGET = Path(__file__).resolve().parent / "dashboard.html"


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def money(value):
    return "INR {:,.0f}".format(float(value or 0))


def bar_chart(items, width=640, bar_height=26, gap=10):
    if not items:
        return ""
    top = max(item["count"] for item in items)
    height = len(items) * (bar_height + gap)
    label_width = 270
    rows = []
    for index, item in enumerate(items):
        y = index * (bar_height + gap)
        length = 0 if top == 0 else int((item["count"] / top) * (width - label_width - 40))
        rows.append(
            '<text x="0" y="{}" class="bar-label">{}</text>'
            '<rect x="{}" y="{}" width="{}" height="{}" rx="3" class="bar"></rect>'
            '<text x="{}" y="{}" class="bar-value">{}</text>'.format(
                y + 18,
                html.escape(item["label"][:46]),
                label_width,
                y + 4,
                max(length, 2),
                bar_height - 8,
                label_width + max(length, 2) + 8,
                y + 18,
                item["count"],
            )
        )
    return '<svg viewBox="0 0 {} {}" class="chart" role="img">{}</svg>'.format(width, height, "".join(rows))


def tile(label, value, note, tone=""):
    return (
        '<div class="tile {}">'
        '<div class="tile-label">{}</div>'
        '<div class="tile-value">{}</div>'
        '<div class="tile-note">{}</div>'
        "</div>"
    ).format(tone, html.escape(label), html.escape(value), html.escape(note))


def build():
    summary = json.loads((OUTPUTS / "summary.json").read_text(encoding="utf-8"))
    metrics = summary["metrics"]
    invoice_rows = read_csv(OUTPUTS / "invoice_status.csv")
    exceptions = read_csv(OUTPUTS / "exceptions.csv")

    stuck = sorted(
        [row for row in invoice_rows if row["stuck_over_12h"] == "Yes"],
        key=lambda row: float(row["hours_since_payment"] or 0),
        reverse=True,
    )
    blocking = [row for row in exceptions if row["blocking"] == "Yes"]
    owners = {}
    for row in blocking:
        owners[row["owner"]] = owners.get(row["owner"], 0) + 1

    reasons = [
        {"label": "{} {}".format(item["code"], item["label"]), "count": item["count"]}
        for item in sorted(summary["exceptions_by_reason"], key=lambda item: (-item["count"], item["code"]))
    ]

    tiles = "".join([
        tile("Stuck invoices over 12h", str(metrics["stuck_invoices_over_12h"]), "of {} paid renewals".format(metrics["paid_invoices"]), "alert" if metrics["stuck_invoices_over_12h"] else ""),
        tile("Blocking exceptions", str(summary["exceptions_blocking"]), "{} owners engaged".format(len(owners))),
        tile("Unscheduled bookings", "{} of {}".format(metrics["unscheduled_bookings"], metrics["bookings_total"]), "{:.0f}% of all bookings".format(metrics["unscheduled_booking_rate"] * 100), "warn"),
        tile("Auto approval rate", "{:.0f}%".format(summary["auto_approval_rate"] * 100), "{} of {} cases".format(summary["auto_approved"], summary["cases"]["total"]), "good"),
        tile("Hours saved per month", "{:.0f}".format(summary["estimated_hours_saved_per_month"]), "at 1,000 renewals, base case", "good"),
        tile("Collected with no class", money(metrics["revenue_without_class_inr"]), "{:.0f}% of collected".format(metrics["class_interruption_rate"] * 100), "alert"),
    ])

    stuck_rows = "".join(
        "<tr><td class='mono'>{}</td><td>{}</td><td class='mono'>{}</td><td>{}</td><td class='mono'>{:.1f}h</td><td><span class='pill'>{}</span></td></tr>".format(
            html.escape(row["invoice_id"]),
            html.escape(row["student_name"]),
            html.escape(row["classbatch_id"]),
            html.escape(row["booking_status"] or "no booking"),
            float(row["hours_since_payment"] or 0),
            html.escape(row["primary_code"]),
        )
        for row in stuck
    )

    owner_rows = "".join(
        "<tr><td>{}</td><td class='mono'>{}</td></tr>".format(html.escape(owner), count)
        for owner, count in sorted(owners.items(), key=lambda item: -item[1])
    )

    exception_rows = "".join(
        "<tr><td class='mono'>{}</td><td>{}</td><td class='mono'>{}</td><td>{}</td><td>{}</td><td class='mono'>{}</td><td class='num'>{:.1f}h</td></tr>".format(
            html.escape(row["case_key"]),
            html.escape(row["student_name"]),
            html.escape(row["primary_code"]),
            html.escape(row["severity"]),
            html.escape(row["owner"]),
            html.escape(row["sla_hours"]),
            float(row["hours_in_state"] or 0),
        )
        for row in sorted(blocking, key=lambda row: -float(row["hours_in_state"] or 0))
    )

    document = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Renewal ops dashboard</title>
<style>
:root {{ --ink:#15191f; --muted:#66707d; --line:#e3e7ec; --bg:#f6f7f9; --card:#ffffff; --accent:#1f5f8b; --good:#1c7c54; --warn:#a8641a; --alert:#a33131; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
header {{ background:#101418; color:#fff; padding:22px 32px; }}
header h1 {{ margin:0 0 4px; font-size:20px; font-weight:600; letter-spacing:-0.2px; }}
header p {{ margin:0; color:#9aa4b0; font-size:12.5px; }}
main {{ padding:24px 32px 40px; max-width:1180px; }}
.tiles {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }}
.tile {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px 16px; }}
.tile-label {{ font-size:11px; text-transform:uppercase; letter-spacing:.7px; color:var(--muted); }}
.tile-value {{ font-size:26px; font-weight:600; margin:6px 0 2px; font-variant-numeric:tabular-nums; }}
.tile-note {{ font-size:11.5px; color:var(--muted); }}
.tile.alert .tile-value {{ color:var(--alert); }}
.tile.warn .tile-value {{ color:var(--warn); }}
.tile.good .tile-value {{ color:var(--good); }}
.grid {{ display:grid; grid-template-columns:1.35fr 1fr; gap:14px; margin-top:18px; }}
section {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:16px 18px; }}
section h2 {{ margin:0 0 12px; font-size:13px; text-transform:uppercase; letter-spacing:.7px; color:var(--muted); font-weight:600; }}
table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
th {{ text-align:left; font-weight:600; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.5px; padding:0 8px 8px 0; border-bottom:1px solid var(--line); }}
td {{ padding:8px 8px 8px 0; border-bottom:1px solid var(--line); }}
tr:last-child td {{ border-bottom:none; }}
.mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.pill {{ display:inline-block; padding:2px 7px; border-radius:99px; background:#eef1f4; font-family:ui-monospace,Menlo,monospace; font-size:11px; }}
.chart {{ width:100%; height:auto; }}
.hint {{ font-size:11px; color:#66707d; margin:-8px 0 8px; }}
.bar {{ fill:#2f6f9e; }}
.bar-label {{ font-size:11.5px; fill:#3a434e; }}
.bar-value {{ font-size:11.5px; fill:#66707d; }}
footer {{ margin-top:18px; font-size:11.5px; color:var(--muted); line-height:1.6; }}
@media print {{ body {{ background:#fff; }} main {{ padding:16px; }} .tile, section {{ break-inside:avoid; }} }}
</style>
</head>
<body>
<header>
  <h1>Renewal operations</h1>
  <p>Data as of {as_of} &middot; engine {version} &middot; {cases} cases &middot; shadow mode</p>
</header>
<main>
  <div class="tiles">{tiles}</div>
  <div class="grid">
    <section>
      <h2>Stuck invoices over 12 hours</h2>
      <table>
        <thead><tr><th>Invoice</th><th>Student</th><th>Batch</th><th>Booking</th><th>Waiting</th><th>Code</th></tr></thead>
        <tbody>{stuck_rows}</tbody>
      </table>
    </section>
    <section>
      <h2>Exceptions by owner</h2>
      <table>
        <thead><tr><th>Owner</th><th>Open</th></tr></thead>
        <tbody>{owner_rows}</tbody>
      </table>
      <h2 style="margin-top:20px">By reason code</h2><p class="hint">Each code fired once in this sample.</p>
      {chart}
    </section>
  </div>
  <div class="grid">
    <section>
      <h2>Open blocking exceptions</h2>
      <table>
        <thead><tr><th>Case</th><th>Student</th><th>Code</th><th>Severity</th><th>Owner</th><th>SLA</th><th>Open</th></tr></thead>
        <tbody>{exception_rows}</tbody>
      </table>
    </section>
    <section>
      <h2>Today's numbers</h2>
      <table>
        <tbody>
          <tr><td>Orphaned invoice rate</td><td class="num">{orphan_rate:.1f}%</td></tr>
          <tr><td>Orphaned value</td><td class="num">{orphan_value}</td></tr>
          <tr><td>Form submission lag, median</td><td class="num">{form_lag:.0f} min</td></tr>
          <tr><td>Approval lag, median</td><td class="num">{approval_lag:.1f} h</td></tr>
          <tr><td>Payment to schedule, median</td><td class="num">{p2s}</td></tr>
          <tr><td>Zero touch eligible</td><td class="num">{zero_touch:.0f}%</td></tr>
          <tr><td>Open exception age, median</td><td class="num">{open_age:.1f} h</td></tr>
          <tr><td>Cost saved per month</td><td class="num">{cost_saved}</td></tr>
        </tbody>
      </table>
    </section>
  </div>
  <footer>
    Stuck means money received and no session row, older than 12 hours. Auto approval rate is cases pushed with no human edit over all cases.
    Payment to schedule has a sample of {p2s_samples}, so read it as an anecdote rather than a baseline.
    Cost saving assumes 1,000 renewals per month at INR 300 per ops hour, editable in engine/savings_assumptions.json.
  </footer>
</main>
</body>
</html>
""".format(
        as_of=summary["data_as_of"],
        version=summary["engine_version"],
        cases=summary["cases"]["total"],
        tiles=tiles,
        stuck_rows=stuck_rows or "<tr><td colspan='6'>None</td></tr>",
        owner_rows=owner_rows or "<tr><td colspan='2'>None</td></tr>",
        chart=bar_chart(reasons),
        exception_rows=exception_rows or "<tr><td colspan='7'>None</td></tr>",
        orphan_rate=metrics["orphaned_invoice_rate"] * 100,
        orphan_value=money(metrics["orphaned_value_inr"]),
        form_lag=metrics["form_submission_lag_hours_median"] * 60,
        approval_lag=metrics["approval_lag_hours_median"],
        p2s="{} h".format(metrics["payment_to_schedule_hours_median"]),
        p2s_samples=metrics["payment_to_schedule_samples"],
        zero_touch=metrics["zero_touch_eligible_rate"] * 100,
        open_age=metrics["open_exception_age_hours_median"],
        cost_saved="INR {:,.0f}".format(summary["estimated_cost_saved_per_month_inr"]),
    )
    TARGET.write_text(document, encoding="utf-8")
    return TARGET


if __name__ == "__main__":
    print(build())
