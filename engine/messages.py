from .normalize import format_date, format_hours, format_money, text
from .reason_codes import CODES
from .rules import AUTO, PROCESSED

PARENT_CHANNEL = "WhatsApp"
TEACHER_CHANNEL = "WhatsApp"
OPS_CHANNEL = "Slack"
FINANCE_CHANNEL = "Slack"
OPS_SLACK = "#renewals-exceptions"
FINANCE_SLACK = "#finance-renewals"


def rupees(value):
    return format_money(value).replace("INR ", "Rs ")


def clock(value):
    raw = text(value)
    return raw[:5] if len(raw) >= 5 else raw


def days_label(value):
    raw = text(value)
    return raw.replace(",", " and ")


def child(row):
    return text(row.get("student_name")) or "your child"


def teacher_name(row):
    return text(row.get("educator_name")) or "there"


def message(row, dataset, channel, audience, recipient, body, escalation):
    return {
        "message_id": "MSG-{}-{}-{}".format(row["case_key"], row["primary_code"], audience),
        "case_key": row["case_key"],
        "reason_code": row["primary_code"],
        "severity": row["severity"],
        "channel": channel,
        "audience": audience,
        "recipient": recipient,
        "message": body,
        "escalation": escalation,
        "data_as_of": row["data_as_of"],
    }


def parent_recipient(invoice):
    mobile = text(invoice.get("mobile"))
    if not mobile:
        return "parent, number missing"
    return "{} (parent WhatsApp)".format(mobile)


def teacher_recipient(row):
    return "{} (teacher WhatsApp on file)".format(teacher_name(row))


def escalation_text(row):
    return "Escalate to {} if unresolved after {}h".format(row["escalates_to"], row["sla_hours"])


def teacher_fyi(row, dataset):
    reference = dataset.reference_by_student.get(text(row.get("student_id")), {})
    body = (
        "{}, {}'s renewal of {} came in on {}. I've put the student back into {} ({} at {}) so no class is missed. No form "
        "needed from you this time."
    ).format(
        teacher_name(row),
        child(row),
        rupees(row["amount_collected"]),
        format_date(row.get("paid_at")),
        text(reference.get("classbatch_name")),
        days_label(reference.get("batch_days")),
        clock(reference.get("batch_start_time")),
    )
    return message(row, dataset, TEACHER_CHANNEL, "teacher", teacher_recipient(row), body, "FYI only")


def teacher_duplicate(row, dataset):
    body = (
        "{}'s renewal form came through twice on {}, the second a few minutes after the first. Same invoice, so I've kept the "
        "first one and closed the second. Nothing to do."
    ).format(child(row), format_date(row.get("paid_at")))
    return message(row, dataset, TEACHER_CHANNEL, "teacher", teacher_recipient(row), body, "FYI only")


def r02_messages(row, dataset):
    body = (
        "Hi {}, quick one on {}'s renewal. The invoice number on the form doesn't match a payment I can find, so I can't "
        "release the classes yet. Could you open the payment receipt and send me the invoice number exactly as it appears? "
        "The number in the confirmation SMS works too."
    ).format(teacher_name(row), child(row))
    out = [message(row, dataset, TEACHER_CHANNEL, "teacher", teacher_recipient(row), body, escalation_text(row))]
    out.append(
        message(
            row,
            dataset,
            OPS_CHANNEL,
            "ops_agent",
            OPS_SLACK,
            (
                "{} {} could not be matched to an invoice. Form {} points at {} and the link at {}. Amount claimed {}, open {}."
            ).format(
                row["case_key"],
                child(row),
                row["record_id"],
                text(row.get("match_method")),
                text(row.get("match_score")),
                rupees(row.get("amount_claimed")),
                format_hours(row["hours_in_state"]),
            ),
            escalation_text(row),
        )
    )
    return out


def r06_messages(row, dataset):
    invoice = dataset.invoices_by_id.get(row["invoice_id"], {})
    return [
        message(
            row,
            dataset,
            PARENT_CHANNEL,
            "parent",
            parent_recipient(invoice),
            (
                "Hi, this is Priya from Bambinos. We have {} for {}'s renewal, which is the first part of the {} fee. I can "
                "start the classes on this payment, but I need a date for the balance before I book the full 24 sessions. "
                "Reply with the date you can pay and I'll set it up the same day."
            ).format(rupees(row["amount_collected"]), child(row), rupees(invoice.get("amount_f"))),
            escalation_text(row),
        ),
        message(
            row,
            dataset,
            FINANCE_CHANNEL,
            "finance",
            FINANCE_SLACK,
            (
                "{} {}. Billed {}, net_amount {}, payment_type {}. The teacher form claims {} paid, which is the full fee, not "
                "what landed. Do not release 24 sessions on this. Decide pro-rated sessions or hold for the balance. Open {}."
            ).format(
                row["case_key"],
                child(row),
                rupees(invoice.get("amount_f")),
                rupees(invoice.get("net_f")),
                text(invoice.get("payment_type")),
                rupees(row.get("amount_claimed")),
                format_hours(row["hours_in_state"]),
            ),
            escalation_text(row),
        ),
    ]


def r07_messages(row, dataset):
    invoice = dataset.invoices_by_id.get(row["invoice_id"], {})
    return [
        message(
            row,
            dataset,
            PARENT_CHANNEL,
            "parent",
            parent_recipient(invoice),
            (
                "Hi, this is Priya from Bambinos. {}'s renewal payment of {} did not go through on {}. Nothing has been "
                "charged. The classes are on hold until it clears, so please retry the same link when you get a minute: {}. "
                "If money did leave your account, send me the reference and I'll trace it today."
            ).format(
                child(row),
                rupees(invoice.get("amount_f")),
                format_date(invoice.get("created_at")),
                text(invoice.get("invoice_link")),
            ),
            escalation_text(row),
        ),
        message(
            row,
            dataset,
            TEACHER_CHANNEL,
            "teacher",
            teacher_recipient(row),
            (
                "{}'s renewal payment failed on {}, so the classes are not scheduled yet. The parent has been asked to retry "
                "the same link. Nothing needed from you, I'll confirm once it clears."
            ).format(child(row), format_date(invoice.get("created_at"))),
            "FYI only",
        ),
    ]


def r08_messages(row, dataset):
    batch = dataset.batches.get(text(row.get("classbatch_id")), {})
    return [
        message(
            row,
            dataset,
            PARENT_CHANNEL,
            "parent",
            parent_recipient(dataset.invoices_by_id.get(row["invoice_id"], {})),
            (
                "Hi, this is Priya from Bambinos. {}'s renewal of {} came through on {}, thank you. The {} batch at {} is full "
                "at {} of {} seats, so I can't put the student back in that slot today. I'm checking with {} whether we can keep "
                "the place or move to another batch. You don't need to do anything right now, and I'll come back to you today "
                "with a firm option."
            ).format(
                child(row),
                rupees(row["amount_collected"]),
                format_date(row.get("paid_at")),
                text(batch.get("class_name")),
                clock(batch.get("batch_start_time")),
                text(batch.get("active_students_count")),
                text(batch.get("max_batch_size")),
                teacher_name(row),
            ),
            escalation_text(row),
        ),
        message(
            row,
            dataset,
            OPS_CHANNEL,
            "ops_agent",
            OPS_SLACK,
            (
                "{} {}. Batch {} ({}) at {}/{} seats. {} cleared {}, open {}. The student is already inside that seat count, so "
                "confirm whether this is a real capacity block. Ask {} ({}) if the batch continues. If yes, renew in place. If "
                "no, offer a batch with a free seat. Parent messaged."
            ).format(
                row["case_key"],
                child(row),
                text(row.get("classbatch_id")),
                text(batch.get("classbatch_name")),
                text(batch.get("active_students_count")),
                text(batch.get("max_batch_size")),
                rupees(row["amount_collected"]),
                format_date(row.get("paid_at")),
                format_hours(row["hours_in_state"]),
                teacher_name(row),
                text(row.get("educator_id")),
            ),
            escalation_text(row),
        ),
    ]


def r09_messages(row, dataset):
    reference = dataset.reference_by_student.get(text(row.get("student_id")), {})
    invoice = dataset.invoices_by_id.get(row["invoice_id"], {})
    booking = dataset.bookings_by_invoice.get(row["invoice_id"], [{}])[0]
    return [
        message(
            row,
            dataset,
            PARENT_CHANNEL,
            "parent",
            parent_recipient(invoice),
            (
                "Hi, this is Priya from Bambinos. {}'s {} renewal is through, thank you. You asked for {} at {} instead of {} "
                "at {}, and I have that noted. I'm matching the student to a batch now. Two things: can you confirm {} works for "
                "the whole term, and should the teacher stay {}? I'll confirm the batch by tomorrow evening."
            ).format(
                child(row),
                rupees(row["amount_collected"]),
                days_label(row.get("preferred_days")) or "the new days",
                clock(row.get("preferred_time")) or "the new time",
                days_label(reference.get("batch_days")),
                clock(reference.get("batch_start_time")),
                clock(row.get("preferred_time")) or "the new time",
                teacher_name(row),
            ),
            escalation_text(row),
        ),
        message(
            row,
            dataset,
            OPS_CHANNEL,
            "ops_agent",
            OPS_SLACK,
            (
                "{} {}. Batch change. Booking at {}. Current batch {} runs {}, parent wants {} at {}. Open {}. Find a batch "
                "with a free seat, confirm teacher continuity with {}, then close the loop with the parent today."
            ).format(
                row["case_key"],
                child(row),
                text(booking.get("request_status")) or "allocation pending",
                text(reference.get("current_classbatch_id")),
                days_label(reference.get("batch_days")),
                days_label(row.get("preferred_days")),
                clock(row.get("preferred_time")),
                format_hours(row["hours_in_state"]),
                teacher_name(row),
            ),
            escalation_text(row),
        ),
    ]


def r12_messages(row, dataset):
    invoice = dataset.invoices_by_id.get(row["invoice_id"], {})
    reference = dataset.reference_by_student.get(text(row.get("student_id")), {})
    form = dataset.forms_by_id.get(row["faculty_form_id"], {})
    return [
        message(
            row,
            dataset,
            PARENT_CHANNEL,
            "parent",
            parent_recipient(invoice),
            (
                "Hi, this is Priya from Bambinos. {}'s renewal of {} came through on {}. The payment shows {}, which is not the "
                "number we have on file, so I want to confirm it is yours before I release the classes. Is that the right "
                "number? Reply yes and I'll get the classes scheduled today."
            ).format(
                child(row),
                rupees(row["amount_collected"]),
                format_date(row.get("paid_at")),
                text(invoice.get("mobile")),
            ),
            escalation_text(row),
        ),
        message(
            row,
            dataset,
            OPS_CHANNEL,
            "ops_agent",
            OPS_SLACK,
            (
                "{} {}. Paid {}, but the payer contact matches neither the registered mobile ({}) nor the registered email "
                "({}). The teacher form gives {}, which matches the registered number, and the remark says the mother paid. "
                "One call confirms it, then release. Open {}."
            ).format(
                row["case_key"],
                child(row),
                rupees(row["amount_collected"]),
                text(reference.get("registered_mobile_masked")),
                text(reference.get("registered_email_masked")),
                text(form.get("parent_mobile")),
                format_hours(row["hours_in_state"]),
            ),
            escalation_text(row),
        ),
    ]


def r20_messages(row, dataset):
    form = dataset.forms_by_id.get(row["faculty_form_id"], {})
    booking = dataset.bookings_by_form.get(row["faculty_form_id"], [{}])[0]
    batch = dataset.batches.get(text(row.get("classbatch_id")), {})
    free = int(batch.get("max_i", 0)) - int(batch.get("active_i", 0))
    body = (
        "{} {}. Approved {}, booking {} still {} after {}. Batch {} has {} seats free ({} of {} used) and {} cleared. One "
        "action closes it: allocate the batch and create the 24 sessions. The parent has had no scheduled class since the "
        "payment."
    ).format(
        row["case_key"],
        child(row),
        format_date(form.get("approved_at")),
        text(booking.get("id")),
        text(booking.get("request_status")),
        format_hours(row["hours_in_state"]),
        text(row.get("classbatch_id")),
        free,
        text(batch.get("active_students_count")),
        text(batch.get("max_batch_size")),
        rupees(row["amount_collected"]),
    )
    return [message(row, dataset, OPS_CHANNEL, "ops_agent", OPS_SLACK, body, escalation_text(row))]


def generic_messages(row, dataset):
    details = CODES[row["primary_code"]]
    invoice = dataset.invoices_by_id.get(row["invoice_id"], {})
    body = (
        "Hi, this is Priya from Bambinos. I'm checking {}'s renewal and found one thing to fix before the classes can be "
        "scheduled: {}. I'm on it and will update you today."
    ).format(child(row), row["reason"].rstrip("."))
    if details["owner"] == "parent":
        return [
            message(row, dataset, PARENT_CHANNEL, "parent", parent_recipient(invoice), body, escalation_text(row)),
            message(row, dataset, OPS_CHANNEL, "ops_agent", OPS_SLACK, row["reason"], escalation_text(row)),
        ]
    if details["owner"] == "teacher":
        return [
            message(row, dataset, TEACHER_CHANNEL, "teacher", teacher_recipient(row), body, escalation_text(row)),
            message(row, dataset, OPS_CHANNEL, "ops_agent", OPS_SLACK, row["reason"], escalation_text(row)),
        ]
    if details["owner"] == "finance":
        return [message(row, dataset, FINANCE_CHANNEL, "finance", FINANCE_SLACK, row["reason"], escalation_text(row))]
    return [message(row, dataset, OPS_CHANNEL, "ops_agent", OPS_SLACK, row["reason"], escalation_text(row))]


BUILDERS = {
    "R02": r02_messages,
    "R06": r06_messages,
    "R07": r07_messages,
    "R08": r08_messages,
    "R09": r09_messages,
    "R12": r12_messages,
    "R20": r20_messages,
}


def payload_for(row, dataset, body):
    reference = dataset.reference_by_student.get(text(row.get("student_id")), {})
    return {
        "audience": None,
        "reason_code": row["primary_code"],
        "reason": row["reason"],
        "student_name": row["student_name"],
        "teacher_name": row["educator_name"],
        "classbatch_id": row["classbatch_id"],
        "batch_name": text(reference.get("classbatch_name")),
        "batch_days": text(reference.get("batch_days")),
        "batch_time": clock(reference.get("batch_start_time")),
        "amount_collected": row["amount_collected"],
        "amount_claimed": row["amount_claimed"],
        "hours_in_state": row["hours_in_state"],
        "sla_hours": row["sla_hours"],
        "escalation_owner": row["escalates_to"],
        "fallback_message": body,
    }


def build_messages(decisions, dataset, polisher=None, stats=None):
    out = []
    for row in decisions:
        if row["record_role"] == "duplicate":
            out.append(teacher_duplicate(row, dataset))
            continue
        if row["decision"] == PROCESSED:
            continue
        if row["decision"] == AUTO:
            if "R01" in row["flags"]:
                out.append(teacher_fyi(row, dataset))
            continue
        builder = BUILDERS.get(row["primary_code"], generic_messages)
        out.extend(builder(row, dataset))
    if polisher:
        used = 0
        for item in out:
            payload = payload_for(
                next(row for row in decisions if row["case_key"] == item["case_key"] and row["primary_code"] == item["reason_code"]),
                dataset,
                item["message"],
            )
            payload["audience"] = item["audience"]
            payload["channel"] = item["channel"]
            polished, applied = polisher("draft_message.md", payload, item["message"])
            if applied:
                item["message"] = polished
                used += 1
        if stats is not None:
            stats["llm_messages"] = used
    return out
