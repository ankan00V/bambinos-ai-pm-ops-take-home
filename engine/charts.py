import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "report" / "charts"
OUTPUTS = ROOT / "outputs"

INK = "#15191f"
MUTED = "#66707d"
LINE = "#dfe4ea"
ACCENT = "#1f5f8b"
LEAK = "#a33131"
GOOD = "#1c7c54"
WARN = "#a8641a"
TRACK = "#eef2f6"
FONT = "-apple-system,BlinkMacSystemFont,Helvetica Neue,Helvetica,Arial,sans-serif"


def esc(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg(width, height, body):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" '
        'font-family="{f}">{b}</svg>'
    ).format(w=width, h=height, f=FONT, b=body)


def label(x, y, value, size=12, fill=INK, anchor="start", weight="400"):
    return '<text x="{x}" y="{y}" font-size="{s}" fill="{c}" text-anchor="{a}" font-weight="{w}">{v}</text>'.format(
        x=x, y=y, s=size, c=fill, a=anchor, w=weight, v=esc(value)
    )


def funnel():
    stages = [
        ("Invoices created", 13, "13 renewal attempts"),
        ("Money received", 12, "11 paid, 1 part paid"),
        ("Form raised", 11, "distinct invoices"),
        ("Approved by Ops", 4, "33% of forms"),
        ("Booking created", 4, "same minute as approval"),
        ("Session rows exist", 1, "one student on the calendar"),
    ]
    width, row, top, label_w = 780, 42, 10, 200
    body = []
    for index, (name, count, note) in enumerate(stages):
        y = top + index * row
        bar = int((count / stages[0][1]) * (width - label_w - 90))
        body.append(label(0, y + 20, name, 12.5, INK, "start", "600"))
        body.append('<rect x="{}" y="{}" width="{}" height="22" rx="3" fill="{}"></rect>'.format(label_w, y + 4, width - label_w - 90, TRACK))
        fill = GOOD if count == stages[0][1] else ACCENT
        body.append('<rect x="{}" y="{}" width="{}" height="22" rx="3" fill="{}"></rect>'.format(label_w, y + 4, max(bar, 3), fill))
        body.append(label(label_w + max(bar, 3) + 10, y + 20, "{}  {}".format(count, note), 11.5, MUTED))
    body.append(
        '<line x1="{}" y1="{}" x2="{}" y2="{}" stroke="{}" stroke-dasharray="3 3"></line>'.format(
            label_w, top + 5 * row - 4, label_w + 60, 220, LEAK
        )
    )
    body.append(label(label_w + 66, top + 5 * row + 2, "", 10, LEAK))
    return svg(width, top + len(stages) * row + 6, "".join(body))


def failures():
    items = [
        ("Paid, no form", 2),
        ("Approved, never scheduled", 2),
        ("Duplicate form", 1),
        ("Part payment", 1),
        ("Failed payment", 1),
        ("Payer contact mismatch", 1),
        ("Batch full", 1),
        ("Batch change", 1),
        ("Invoice typo repaired", 1),
    ]
    width, row, top, label_w = 780, 30, 6, 220
    body = []
    for index, (name, count) in enumerate(items):
        y = top + index * row
        length = int((count / 2) * (width - label_w - 70))
        body.append(label(0, y + 16, name, 12, INK))
        body.append('<rect x="{}" y="{}" width="{}" height="16" rx="3" fill="{}"></rect>'.format(label_w, y + 4, width - label_w - 70, TRACK))
        body.append('<rect x="{}" y="{}" width="{}" height="16" rx="3" fill="{}"></rect>'.format(label_w, y + 4, max(length, 3), LEAK))
        body.append(label(label_w + max(length, 3) + 10, y + 17, count, 12, MUTED))
    return svg(width, top + len(items) * row + 4, "".join(body))


def timing():
    rows = [
        ("Payment to form", 14.8, 27.1, 49.8, 10),
        ("Form to approval", 45.0, 92.4, 150.0, 4),
        ("Approval to first session", 30.1, 30.1, 30.1, 1),
    ]
    width, height, left, right = 780, 190, 210, 60
    scale = (width - left - right) / 160.0
    body = []
    for tick in range(0, 161, 30):
        x = left + tick * scale
        body.append('<line x1="{x}" y1="26" x2="{x}" y2="140" stroke="{c}" stroke-width="1"></line>'.format(x=x, c=LINE))
        body.append(label(x, 158, "{}m".format(tick), 10.5, MUTED, "middle"))
    for index, (name, low, mid, high, samples) in enumerate(rows):
        y = 44 + index * 32
        body.append(label(0, y + 4, name, 12, INK))
        body.append(label(0, y + 19, "n={}".format(samples), 10, MUTED))
        x1 = left + low * scale
        x2 = left + high * scale
        body.append('<line x1="{}" y1="{}" x2="{}" y2="{}" stroke="{}" stroke-width="2"></line>'.format(x1, y, x2, y, ACCENT))
        body.append('<circle cx="{}" cy="{}" r="5" fill="{}"></circle>'.format(left + mid * scale, y, INK))
        body.append(label(x2 + 8, y + 4, "{}m median".format(int(mid)), 10.5, MUTED))
    return svg(width, height, "".join(body))


def savings():
    data = json.loads((OUTPUTS / "savings_model.json").read_text(encoding="utf-8"))
    today = data["scenarios"]["base"]["hours_today_per_month"]
    bars = [
        ("Today", today, MUTED),
        ("After, 55%", data["scenarios"]["low"]["hours_new_per_month"], ACCENT),
        ("After, 70%", data["scenarios"]["base"]["hours_new_per_month"], GOOD),
        ("After, 80%", data["scenarios"]["high"]["hours_new_per_month"], GOOD),
    ]
    width, height, base_y, left = 780, 250, 190, 60
    body = []
    body.append('<line x1="{}" y1="{}" x2="{}" y2="{}" stroke="{}"></line>'.format(left, base_y, width - 20, base_y, LINE))
    body.append(label(0, 20, "Ops hours per month at 1,000 renewals", 11, MUTED))
    slot = (width - left - 30) / len(bars)
    for index, (name, value, color) in enumerate(bars):
        x = left + index * slot + 18
        bar = int((value / today) * 120)
        body.append('<rect x="{}" y="{}" width="{}" height="{}" rx="3" fill="{}"></rect>'.format(x, base_y - bar, slot - 46, bar, color))
        body.append(label(x + (slot - 46) / 2, base_y - bar - 8, "{:.0f}h".format(value), 12, INK, "middle", "600"))
        body.append(label(x + (slot - 46) / 2, base_y + 18, name, 10.5, MUTED, "middle"))
    body.append(label(left, base_y + 46, "Base case saves {:.0f} hours a month, about INR {:,} at INR 300 an hour.".format(
        data["scenarios"]["base"]["hours_saved_per_month"],
        data["scenarios"]["base"]["cost_saved_per_month_inr"],
    ), 11, MUTED))
    return svg(width, height, "".join(body))


def box(x, y, w, h, title, subtitle, stroke=LINE, fill="#ffffff", title_color=INK):
    return (
        '<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{f}" stroke="{s}" stroke-width="1.2"></rect>'
        '{t}{sub}'
    ).format(
        x=x, y=y, w=w, h=h, f=fill, s=stroke,
        t=label(x + 16, y + 28, title, 13, title_color, "start", "600"),
        sub=label(x + 16, y + 48, subtitle, 10.5, MUTED),
    )


def arrow(x1, y1, x2, y2, color=MUTED, dashed=False):
    style = ' stroke-dasharray="5 4"' if dashed else ""
    return (
        '<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c}" stroke-width="1.6"{s} '
        'marker-end="url(#head)"></line>'
    ).format(x1=x1, y1=y1, x2=x2, y2=y2, c=color, s=style)


def defs():
    return (
        '<defs><marker id="head" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
        '<path d="M0,0 L10,5 L0,10 z" fill="{c}"></path></marker></defs>'
    ).format(c=MUTED)


def flow_before():
    width, height = 860, 440
    body = [defs()]
    steps = [
        ("Invoice paid", "Parent, through the gateway", 34),
        ("Renewal form filled", "Teacher, by hand, copying the invoice", 140),
        ("Approved and booked", "Ops team, checking the payment", 246),
        ("Batch allocated", "Parent or Ops picks a slot", 352),
    ]
    for name, subtitle, y in steps:
        body.append(box(40, y, 260, 64, name, subtitle))
    for y in (98, 204, 310):
        body.append(arrow(170, y, 170, y + 40))
    notes = [
        (112, "2 of 12 paid invoices never got a form", "INR 29,000 waiting on a teacher's admin"),
        (218, "8 of 12 forms unapproved at the snapshot", "median 1.5h once picked up, oldest 32.5h"),
        (324, "2 of 4 bookings never produced a session", "INR 21,500 paid, no class on the calendar"),
    ]
    for y, headline, detail in notes:
        body.append('<rect x="330" y="{}" width="6" height="34" rx="3" fill="{}"></rect>'.format(y - 14, LEAK))
        body.append(label(348, y, headline, 11.5, LEAK, "start", "600"))
        body.append(label(348, y + 17, detail, 10.5, MUTED))
    body.append(label(40, 22, "As it runs today", 11, MUTED, "start", "600"))
    return svg(width, height, "".join(body))


def flow_after():
    width, height = 900, 420
    body = [defs()]
    body.append(label(20, 22, "After the redesign", 11, MUTED, "start", "600"))
    body.append(box(20, 160, 170, 74, "Payment gateway", "the only source of truth"))
    body.append(box(250, 160, 200, 74, "Reconciliation engine", "rules every 15 minutes"))
    body.append(arrow(190, 197, 246, 197))
    body.append(box(510, 40, 370, 96, "Fast lane, no human", "same-batch seat retained; identity matched", GOOD, "#f4faf7"))
    body.append(label(526, 106, "75.0% of paid renewals: booking plus 24 sessions", 10.5, GOOD))
    body.append(box(510, 280, 370, 96, "Exception lane, one owner", "new allocation, part payment, payer mismatch, batch change", WARN, "#fdf8f1"))
    body.append(label(526, 346, "25.0% of paid renewals: owner, SLA, drafted message", 10.5, WARN))
    body.append('<path d="M450,180 C480,180 480,100 506,98" fill="none" stroke="{}" stroke-width="1.6" marker-end="url(#head)"></path>'.format(GOOD))
    body.append('<path d="M450,214 C480,214 480,320 506,322" fill="none" stroke="{}" stroke-width="1.6" marker-end="url(#head)"></path>'.format(WARN))
    body.append(box(250, 300, 200, 64, "Teacher form", "optional corroboration, never the trigger", LINE, "#fbfcfd"))
    body.append(arrow(350, 300, 350, 238, MUTED, True))
    body.append(label(360, 272, "dashed: no longer gates anything", 10, MUTED))
    return svg(width, height, "".join(body))


def write(name, content):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(content, encoding="utf-8")


def main():
    write("funnel.svg", funnel())
    write("failures.svg", failures())
    write("timing.svg", timing())
    write("savings.svg", savings())
    write("flow_before.svg", flow_before())
    write("flow_after.svg", flow_after())
    for path in sorted(OUT.glob("*.svg")):
        print("{} {} bytes".format(path.name, path.stat().st_size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
