import csv
import json
from pathlib import Path

from . import config
from .load import load_dataset
from .messages import build_messages
from .normalize import format_date, format_hours, format_money
from .reason_codes import CODES
from .rules import AUTO, EXCEPTION, PROCESSED, evaluate
from .savings import build_savings
from .status import build_invoice_status, build_metrics

AUTO_FIELDS = [
    "action",
    "case_key",
    "evidence",
    "invoice_id",
    "faculty_form_id",
    "student_id",
    "student_name",
    "user_id",
    "class_id",
    "classbatch_id",
    "educator_id",
    "educator_name",
    "sessions_count",
    "continue_same_batch",
    "preferred_days",
    "preferred_time",
    "amount_collected",
    "currency",
    "paid_at",
    "seats_left_after",
    "primary_code",
    "flags",
    "reason",
    "match_method",
    "data_as_of",
]

EXCEPTION_FIELDS = [
    "case_key",
    "record_type",
    "record_id",
    "record_role",
    "invoice_id",
    "faculty_form_id",
    "student_id",
    "student_name",
    "educator_id",
    "educator_name",
    "classbatch_id",
    "amount_collected",
    "amount_claimed",
    "currency",
    "payment_status",
    "paid_at",
    "primary_code",
    "reason_code_label",
    "secondary_codes",
    "severity",
    "blocking",
    "owner",
    "escalates_to",
    "sla_hours",
    "hours_in_state",
    "recommended_action",
    "reason",
    "message_channels",
    "data_as_of",
]

MESSAGE_FIELDS = [
    "message_id",
    "case_key",
    "reason_code",
    "severity",
    "channel",
    "audience",
    "recipient",
    "message",
    "escalation",
    "data_as_of",
]

DECISION_FIELDS = [
    "case_key",
    "record_type",
    "record_id",
    "record_role",
    "source",
    "evidence",
    "invoice_id",
    "faculty_form_id",
    "student_id",
    "student_name",
    "class_id",
    "classbatch_id",
    "educator_id",
    "educator_name",
    "amount_collected",
    "amount_claimed",
    "currency",
    "paid_at",
    "payment_status",
    "decision",
    "primary_code",
    "secondary_codes",
    "severity",
    "blocking",
    "owner",
    "escalates_to",
    "sla_hours",
    "hours_in_state",
    "recommended_action",
    "reason",
    "match_method",
    "match_score",
    "seats_left_after",
    "data_as_of",
]

STATUS_FIELDS = [
    "invoice_id",
    "invoice_number",
    "student_id",
    "student_name",
    "educator_id",
    "educator_name",
    "classbatch_id",
    "seats_used",
    "seats_max",
    "amount_collected",
    "currency",
    "payment_status",
    "payment_type",
    "paid_at",
    "hours_since_payment",
    "form_count",
    "booking_count",
    "booking_status",
    "session_rows",
    "future_sessions",
    "stage",
    "stuck_over_12h",
    "interruption_risk",
    "decision",
    "primary_code",
]


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def build_summary(dataset, decisions, invoice_rows, metrics, savings, messages, llm_used=False):
    case_rows = [row for row in decisions if row["record_role"] == "primary"]
    exception_rows = [row for row in decisions if row["decision"] == EXCEPTION]
    blocking = [row for row in exception_rows if row["blocking"] == "Yes"]

    reason_counts = {}
    for row in exception_rows:
        reason_counts[row["primary_code"]] = reason_counts.get(row["primary_code"], 0) + 1

    exceptions_by_reason = []
    for code in sorted(reason_counts):
        rows_for_code = [row for row in exception_rows if row["primary_code"] == code]
        exceptions_by_reason.append(
            {
                "code": code,
                "label": CODES[code]["label"],
                "count": reason_counts[code],
                "owner": CODES[code]["owner"],
                "severity": CODES[code]["severity"],
                "blocking": "Yes" if any(row["blocking"] == "Yes" for row in rows_for_code) else "No",
            }
        )

    by_owner = {}
    for row in blocking:
        by_owner[row["owner"]] = by_owner.get(row["owner"], 0) + 1

    flag_counts = {}
    for row in decisions:
        for code in [item for item in row["flags"].split(",") if item]:
            flag_counts[code] = flag_counts.get(code, 0) + 1

    return {
        "engine_version": config.ENGINE_VERSION,
        "data_as_of": dataset.as_of.strftime("%Y-%m-%d %H:%M:%S"),
        "cases": {
            "total": len(case_rows),
            "auto_approved": len([row for row in case_rows if row["decision"] == AUTO]),
            "exceptions": len([row for row in case_rows if row["decision"] == EXCEPTION]),
            "already_processed": len([row for row in case_rows if row["decision"] == PROCESSED]),
        },
        "auto_approved": len([row for row in case_rows if row["decision"] == AUTO]),
        "auto_approval_rate": metrics["auto_approval_rate"],
        "zero_touch_eligible_rate": metrics["zero_touch_eligible_rate"],
        "exceptions_total": len(exception_rows),
        "exceptions_blocking": len(blocking),
        "exceptions_by_reason": exceptions_by_reason,
        "exceptions_by_owner": by_owner,
        "flags": flag_counts,
        "messages_drafted": len(messages),
        "estimated_hours_saved_per_month": savings["base"]["hours_saved_per_month"],
        "estimated_cost_saved_per_month_inr": savings["base"]["cost_saved_per_month_inr"],
        "savings": savings,
        "metrics": metrics,
        "llm_used": llm_used,
        "limits": [
            "All names, phones and emails in the source files are masked, so fuzzy name matching is weak by construction and phone matching relies on the last visible digits.",
            "The schedule table holds 2 rows for 12 paid renewals. Class interruption rate and payment to schedule turnaround are therefore computed on a partial export and should be re-run on a full schedule export before being quoted to the business.",
            "Payment gateway settlement is taken from the invoice row. The engine never calls Razorpay or Stripe, so a paid status that is later reversed would not be caught.",
            "Teacher phone numbers are not in the dataset, so WhatsApp recipients for teachers are names plus the staff directory in production.",
            "The savings model is a volume scenario at 1,000 renewals per month. Observed volume in the file is 13 cases over 3 days.",
        ],
    }


def build_markdown(messages, summary):
    lines = []
    lines.append("# Drafted messages")
    lines.append("")
    lines.append(
        "{} drafts across {} exceptions, generated from data as of {}. Names and numbers appear masked because the source files are masked.".format(
            summary["messages_drafted"], summary["exceptions_total"], summary["data_as_of"]
        )
    )
    lines.append("")
    current = None
    for row in messages:
        if row["case_key"] != current:
            current = row["case_key"]
            lines.append("## Case {}".format(current))
            lines.append("")
        lines.append("**{} to {}** ({})".format(row["channel"], row["audience"], row["reason_code"]))
        lines.append("")
        lines.append("To: {}".format(row["recipient"]))
        lines.append("")
        lines.append("> {}".format(row["message"]))
        lines.append("")
        lines.append("Escalation: {}".format(row["escalation"]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_savings_rows(savings):
    base = savings["base"]
    rows = [
        {"line_item": "Monthly renewal volume (assumption)", "value": savings["assumptions"]["monthly_renewals"], "unit": "cases", "note": "Editable in engine/savings_assumptions.json"},
        {"line_item": "Observed manual minutes per case", "value": base["manual_mean_minutes"], "unit": "minutes", "note": "Weighted by the reason code mix in this dataset"},
        {"line_item": "Manual minutes with context switching", "value": base["today_minutes_per_case"], "unit": "minutes", "note": "Adds the context switch allowance"},
        {"line_item": "New minutes per case at base auto rate", "value": base["new_minutes_per_case"], "unit": "minutes", "note": "Auto rate {} percent".format(int(base["auto_approval_rate"] * 100))},
        {"line_item": "Hours today", "value": base["hours_today_per_month"], "unit": "hours/month", "note": "Monthly volume times manual minutes"},
        {"line_item": "Hours after automation", "value": base["hours_new_per_month"], "unit": "hours/month", "note": ""},
        {"line_item": "Hours saved", "value": base["hours_saved_per_month"], "unit": "hours/month", "note": ""},
        {"line_item": "Hours saved", "value": base["hours_saved_per_year"], "unit": "hours/year", "note": ""},
        {"line_item": "Cost today", "value": base["cost_today_per_month_inr"], "unit": "INR/month", "note": "At the assumed loaded hourly cost"},
        {"line_item": "Cost after automation", "value": base["cost_new_per_month_inr"], "unit": "INR/month", "note": ""},
        {"line_item": "Cost saved", "value": base["cost_saved_per_month_inr"], "unit": "INR/month", "note": ""},
        {"line_item": "Cost saved", "value": base["cost_saved_per_year_inr"], "unit": "INR/year", "note": ""},
        {"line_item": "One time build cost (assumption)", "value": savings["assumptions"]["one_time_build_cost_inr"], "unit": "INR", "note": "Six weeks of one engineer plus part of an ops lead"},
        {"line_item": "Payback", "value": base["payback_months"], "unit": "months", "note": "Build cost divided by monthly labour saving"},
    ]
    for name in ("low", "base", "high"):
        item = savings["scenarios"][name]
        rows.append(
            {
                "line_item": "Sensitivity at {} percent auto approval".format(int(item["auto_approval_rate"] * 100)),
                "value": item["hours_saved_per_month"],
                "unit": "hours/month",
                "note": "Cost saved {} INR per month".format(item["cost_saved_per_month_inr"]),
            }
        )
    return rows


def run(data_dir=None, output_dir=None, use_llm=False):
    dataset = load_dataset(data_dir)
    decisions = evaluate(dataset)
    invoice_rows = build_invoice_status(dataset, decisions)
    stats = {}
    polisher = None
    if use_llm:
        from .llm import is_available, polish

        if is_available():
            polisher = polish
    messages = build_messages(decisions, dataset, polisher, stats)
    savings = build_savings(decisions, None)
    metrics = build_metrics(dataset, decisions, invoice_rows)
    summary = build_summary(dataset, decisions, invoice_rows, metrics, savings, messages, bool(stats.get("llm_messages")))

    out = Path(output_dir) if output_dir else config.OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    auto_rows = []
    for row in decisions:
        if row["decision"] != AUTO:
            continue
        auto_rows.append(
            {
                "action": "insert_booking",
                "case_key": row["case_key"],
                "evidence": row["evidence"],
                "invoice_id": row["invoice_id"],
                "faculty_form_id": row["faculty_form_id"],
                "student_id": row["student_id"],
                "student_name": row["student_name"],
                "user_id": row["user_id"],
                "class_id": row["class_id"],
                "classbatch_id": row["classbatch_id"],
                "educator_id": row["educator_id"],
                "educator_name": row["educator_name"],
                "sessions_count": row["sessions_count"],
                "continue_same_batch": row["continue_same_batch"],
                "preferred_days": row["preferred_days"],
                "preferred_time": row["preferred_time"],
                "amount_collected": row["amount_collected"],
                "currency": row["currency"],
                "paid_at": row["paid_at"],
                "seats_left_after": row["seats_left_after"],
                "primary_code": row["primary_code"],
                "flags": row["flags"],
                "reason": row["reason"],
                "match_method": row["match_method"],
                "data_as_of": row["data_as_of"],
            }
        )

    channels = {}
    for row in messages:
        channels.setdefault(row["case_key"], []).append("{}:{}".format(row["channel"], row["audience"]))

    exception_rows = []
    for row in decisions:
        if row["decision"] != EXCEPTION:
            continue
        exception_rows.append(
            {
                "case_key": row["case_key"],
                "record_type": row["record_type"],
                "record_id": row["record_id"],
                "record_role": row["record_role"],
                "invoice_id": row["invoice_id"],
                "faculty_form_id": row["faculty_form_id"],
                "student_id": row["student_id"],
                "student_name": row["student_name"],
                "educator_id": row["educator_id"],
                "educator_name": row["educator_name"],
                "classbatch_id": row["classbatch_id"],
                "amount_collected": row["amount_collected"],
                "amount_claimed": row["amount_claimed"],
                "currency": row["currency"],
                "payment_status": row["payment_status"],
                "paid_at": row["paid_at"],
                "primary_code": row["primary_code"],
                "reason_code_label": CODES[row["primary_code"]]["label"],
                "secondary_codes": row["secondary_codes"],
                "severity": row["severity"],
                "blocking": row["blocking"],
                "owner": row["owner"],
                "escalates_to": row["escalates_to"],
                "sla_hours": row["sla_hours"],
                "hours_in_state": row["hours_in_state"],
                "recommended_action": row["recommended_action"],
                "reason": row["reason"],
                "message_channels": ", ".join(sorted(set(channels.get(row["case_key"], [])))),
                "data_as_of": row["data_as_of"],
            }
        )

    write_csv(out / "auto_approved.csv", auto_rows, AUTO_FIELDS)
    write_csv(out / "exceptions.csv", exception_rows, EXCEPTION_FIELDS)
    write_csv(out / "messages.csv", messages, MESSAGE_FIELDS)
    write_csv(out / "decisions.csv", decisions, DECISION_FIELDS)
    write_csv(out / "invoice_status.csv", invoice_rows, STATUS_FIELDS)
    write_csv(out / "savings_model.csv", build_savings_rows(savings), ["line_item", "value", "unit", "note"])
    write_json(out / "savings_model.json", savings)
    write_json(out / "summary.json", summary)

    with open(out / "messages.md", "w", encoding="utf-8") as handle:
        handle.write(build_markdown(messages, summary))

    return summary


def describe(summary):
    metrics = summary["metrics"]
    lines = []
    lines.append("Bambinos renewal reconciliation engine {}".format(summary["engine_version"]))
    lines.append("Data as of {}".format(summary["data_as_of"]))
    lines.append("")
    lines.append("Cases                 {}".format(summary["cases"]["total"]))
    lines.append("Auto approved         {} ({:.1f} percent)".format(summary["auto_approved"], summary["auto_approval_rate"] * 100))
    lines.append("Blocking exceptions   {}".format(summary["exceptions_blocking"]))
    lines.append("Informational rows    {}".format(summary["exceptions_total"] - summary["exceptions_blocking"]))
    lines.append("Already processed     {}".format(summary["cases"]["already_processed"]))
    lines.append("Zero touch eligible   {:.1f} percent of paid invoices".format(summary["zero_touch_eligible_rate"] * 100))
    lines.append("")
    lines.append("Orphaned invoices     {} of {} paid ({:.1f} percent), {} at risk".format(
        metrics["orphaned_invoices"],
        metrics["paid_invoices"],
        metrics["orphaned_invoice_rate"] * 100,
        format_money(metrics["orphaned_value_inr"]),
    ))
    lines.append("Stuck over 12 hours   {} of {} paid".format(metrics["stuck_invoices_over_12h"], metrics["paid_invoices"]))
    lines.append("No future class       {} of {} paid ({:.1f} percent), {} collected".format(
        metrics["paid_with_no_future_class"],
        metrics["paid_invoices"],
        metrics["class_interruption_rate"] * 100,
        format_money(metrics["revenue_without_class_inr"]),
    ))
    lines.append("Form lag median       {}".format(format_hours(metrics["form_submission_lag_hours_median"] or 0)))
    lines.append("Approval lag median   {}".format(format_hours(metrics["approval_lag_hours_median"] or 0)))
    lines.append("Payment to schedule   {} (n={})".format(
        format_hours(metrics["payment_to_schedule_hours_median"] or 0), metrics["payment_to_schedule_samples"]
    ))
    lines.append("")
    lines.append("Exceptions by reason")
    for item in summary["exceptions_by_reason"]:
        lines.append("  {} {:<45} {:>2}  {}".format(item["code"], item["label"], item["count"], item["owner"]))
    lines.append("")
    lines.append("Hours saved per month {}".format(summary["estimated_hours_saved_per_month"]))
    lines.append("Cost saved per month  INR {:,}".format(summary["estimated_cost_saved_per_month_inr"]))
    return "\n".join(lines)
