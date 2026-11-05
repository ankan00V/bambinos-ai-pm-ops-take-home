from statistics import median

from . import config
from .normalize import hours_between, text, to_float, to_int
from .rules import AUTO, EXCEPTION, PROCESSED, ZERO_TOUCH_CODES


def build_invoice_status(dataset, decisions):
    case_rows = {row["case_key"]: row for row in decisions if row["record_role"] == "primary"}
    form_counts = {}
    for row in decisions:
        if row["record_type"] == "form":
            form_counts[row["case_key"]] = form_counts.get(row["case_key"], 0) + 1

    rows = []
    for invoice in dataset.invoices:
        invoice_id = text(invoice.get("id"))
        decision = case_rows.get(invoice_id)
        batch = dataset.batch_of(invoice.get("student_id"))
        bookings = dataset.bookings_by_invoice.get(invoice_id, [])
        sessions = dataset.schedule_by_invoice.get(invoice_id, [])
        future = dataset.future_sessions(invoice_id)
        hours = hours_between(invoice.get("paid_dt"), dataset.as_of)
        settled = text(invoice.get("payment_status")).lower() in {"paid", "partially_paid"}
        booking_status = ", ".join(sorted({text(b.get("request_status")) for b in bookings})) if bookings else ""

        if not settled:
            stage = "no payment"
        elif future > 0:
            stage = "scheduled"
        elif decision and decision["decision"] == EXCEPTION:
            stage = "blocked"
        else:
            stage = "awaiting schedule"

        rows.append(
            {
                "invoice_id": invoice_id,
                "invoice_number": text(invoice.get("invoice_number")),
                "student_id": text(invoice.get("student_id")),
                "student_name": text((dataset.reference_by_student.get(text(invoice.get("student_id"))) or {}).get("student_name_masked")),
                "educator_id": text(invoice.get("educator_id")),
                "educator_name": text((batch or {}).get("educator_name")),
                "classbatch_id": text((batch or {}).get("current_classbatch_id")),
                "seats_used": to_int((batch or {}).get("active_students_count")),
                "seats_max": to_int((batch or {}).get("max_batch_size")),
                "amount_collected": invoice["net_f"],
                "currency": text(invoice.get("currency")),
                "payment_status": text(invoice.get("payment_status")),
                "payment_type": text(invoice.get("payment_type")),
                "paid_at": text(invoice.get("paid_at")),
                "hours_since_payment": hours if hours is not None else "",
                "form_count": form_counts.get(invoice_id, 0),
                "booking_count": len(bookings),
                "booking_status": booking_status,
                "session_rows": len(sessions),
                "future_sessions": future,
                "stage": stage,
                "stuck_over_12h": "Yes" if settled and future == 0 and (hours or 0) >= config.STUCK_INVOICE_HOURS else "No",
                "interruption_risk": "Yes" if settled and future == 0 else "No",
                "decision": decision["decision"] if decision else "",
                "primary_code": decision["primary_code"] if decision else "",
            }
        )
    return rows


def build_metrics(dataset, decisions, invoice_rows):
    money_rows = [row for row in invoice_rows if row["payment_status"].lower() in {"paid", "partially_paid"}]
    orphan_rows = [row for row in money_rows if row["form_count"] == 0]
    stuck_rows = [row for row in money_rows if row["stuck_over_12h"] == "Yes"]
    interruption_rows = [row for row in money_rows if row["interruption_risk"] == "Yes"]

    form_lags = []
    approval_lags = []
    for form in dataset.forms:
        invoice = dataset.invoices_by_id.get(text(form.get("invoice_id")))
        if invoice and invoice.get("paid_dt") and form.get("created_dt"):
            lag = hours_between(invoice["paid_dt"], form["created_dt"])
            if lag is not None and lag >= 0:
                form_lags.append(lag)
        if form.get("created_dt") and form.get("approved_dt"):
            lag = hours_between(form["created_dt"], form["approved_dt"])
            if lag is not None and lag >= 0:
                approval_lags.append(lag)

    payment_to_schedule = []
    for invoice in dataset.invoices:
        sessions = dataset.schedule_by_invoice.get(text(invoice.get("id")), [])
        if sessions and invoice.get("paid_dt"):
            first = min(row["created_dt"] for row in sessions if row.get("created_dt"))
            lag = hours_between(invoice["paid_dt"], first)
            if lag is not None:
                payment_to_schedule.append(lag)

    unscheduled = [row for row in dataset.bookings if not dataset.schedule_by_booking.get(text(row.get("id")))]
    case_rows = [row for row in decisions if row["record_role"] == "primary"]
    auto_cases = [row for row in case_rows if row["decision"] == AUTO]
    exception_cases = [row for row in case_rows if row["decision"] == EXCEPTION]
    blocking_cases = [row for row in exception_cases if row["blocking"] == "Yes"]
    zero_touch = [row for row in money_rows if row["primary_code"] in ZERO_TOUCH_CODES]

    open_ages = [row["hours_in_state"] for row in blocking_cases]

    metrics = {
        "cases_total": len(case_rows),
        "paid_invoices": len(money_rows),
        "orphaned_invoices": len(orphan_rows),
        "orphaned_invoice_rate": round(len(orphan_rows) / len(money_rows), 4) if money_rows else 0.0,
        "orphaned_value_inr": round(sum(row["amount_collected"] for row in orphan_rows), 2),
        "stuck_invoices_over_12h": len(stuck_rows),
        "stuck_invoice_rate": round(len(stuck_rows) / len(money_rows), 4) if money_rows else 0.0,
        "paid_with_no_future_class": len(interruption_rows),
        "class_interruption_rate": round(len(interruption_rows) / len(money_rows), 4) if money_rows else 0.0,
        "revenue_without_class_inr": round(sum(row["amount_collected"] for row in interruption_rows), 2),
        "collected_total_inr": round(sum(row["amount_collected"] for row in money_rows), 2),
        "form_submission_lag_hours_median": round(median(form_lags), 2) if form_lags else None,
        "form_submission_lag_samples": len(form_lags),
        "approval_lag_hours_median": round(median(approval_lags), 2) if approval_lags else None,
        "approval_lag_samples": len(approval_lags),
        "payment_to_schedule_hours_median": round(median(payment_to_schedule), 2) if payment_to_schedule else None,
        "payment_to_schedule_samples": len(payment_to_schedule),
        "unscheduled_booking_rate": round(len(unscheduled) / len(dataset.bookings), 4) if dataset.bookings else 0.0,
        "unscheduled_bookings": len(unscheduled),
        "bookings_total": len(dataset.bookings),
        "auto_approved_cases": len(auto_cases),
        "auto_approval_rate": round(len(auto_cases) / len(case_rows), 4) if case_rows else 0.0,
        "zero_touch_eligible_cases": len(zero_touch),
        "zero_touch_eligible_rate": round(len(zero_touch) / len(money_rows), 4) if money_rows else 0.0,
        "exceptions_blocking": len(blocking_cases),
        "exceptions_informational": len(exception_cases) - len(blocking_cases),
        "open_exception_age_hours_median": round(median(open_ages), 1) if open_ages else 0.0,
        "open_exception_age_hours_max": round(max(open_ages), 1) if open_ages else 0.0,
        "first_pass_auto_approval_baseline": 0.0,
        "already_processed_cases": len([row for row in case_rows if row["decision"] == PROCESSED]),
    }
    return metrics
