from . import config
from .matching import resolve_invoice
from .normalize import email_score, format_date, format_hours, format_money, phone_country, phone_score, text, to_float, to_int
from .reason_codes import CODES

AUTO = "AUTO_APPROVE"
EXCEPTION = "EXCEPTION"
PROCESSED = "ALREADY_PROCESSED"

ZERO_TOUCH_CODES = {"R00", "R17", "R20"}


def new_decision(case_key, record_type, record_id, dataset):
    return {
        "case_key": case_key,
        "record_type": record_type,
        "record_id": record_id,
        "record_role": "primary",
        "source": "",
        "evidence": "",
        "invoice_id": "",
        "faculty_form_id": "",
        "student_id": "",
        "student_name": "",
        "user_id": "",
        "class_id": "",
        "classbatch_id": "",
        "educator_id": "",
        "educator_name": "",
        "sessions_count": "",
        "continue_same_batch": "",
        "preferred_days": "",
        "preferred_time": "",
        "amount_collected": 0.0,
        "amount_claimed": "",
        "currency": "",
        "paid_at": "",
        "payment_status": "",
        "decision": "",
        "primary_code": "",
        "secondary_codes": "",
        "flags": [],
        "severity": "",
        "blocking": "No",
        "owner": "",
        "escalates_to": "",
        "sla_hours": 0,
        "hours_in_state": 0.0,
        "recommended_action": "",
        "reason": "",
        "match_method": "",
        "match_score": "",
        "seats_left_after": "",
        "data_as_of": dataset.as_of.strftime("%Y-%m-%d %H:%M:%S"),
        "_state_since": None,
    }


def block(row, code, reason):
    details = CODES[code]
    row["decision"] = EXCEPTION
    row["primary_code"] = code
    row["severity"] = details["severity"]
    row["blocking"] = "Yes"
    row["owner"] = details["owner"]
    row["escalates_to"] = details["escalates_to"]
    row["sla_hours"] = details["sla_hours"]
    row["recommended_action"] = details["action"]
    row["reason"] = reason
    return row


def approve(row, reason):
    details = CODES["R00"]
    row["decision"] = AUTO
    row["primary_code"] = "R00"
    row["severity"] = "Info"
    row["blocking"] = "No"
    row["owner"] = "system"
    row["escalates_to"] = details["escalates_to"]
    row["sla_hours"] = 0
    row["recommended_action"] = details["action"]
    row["reason"] = reason
    return row


def flag(row, code):
    if code not in row["flags"]:
        row["flags"].append(code)


def payment_is_settled(invoice):
    return text(invoice.get("payment_status")).lower() in {"paid", "partially_paid"}


def seats_available(dataset, batch_id):
    batch = dataset.batches.get(text(batch_id))
    if not batch:
        return None
    return to_int(batch.get("max_batch_size")) - to_int(batch.get("active_students_count"))


def age_hours(row, dataset):
    since = row.get("_state_since")
    if not since:
        return 0.0
    return (dataset.as_of - since).total_seconds() / 3600.0


def identity_scores(invoice, reference):
    phone = phone_score(invoice.get("mobile"), reference.get("registered_mobile_masked"))
    email = email_score(invoice.get("email"), reference.get("registered_email_masked"))
    return phone, email


def evaluate_invoice_only(invoice, dataset):
    row = new_decision(text(invoice.get("id")), "invoice", text(invoice.get("id")), dataset)
    row["source"] = "invoice"
    row["evidence"] = "invoice only"
    row["invoice_id"] = text(invoice.get("id"))
    row["student_id"] = text(invoice.get("student_id"))
    row["user_id"] = text(invoice.get("user_id"))
    row["class_id"] = text(invoice.get("class_id"))
    row["educator_id"] = text(invoice.get("educator_id"))
    row["amount_collected"] = invoice["net_f"]
    row["currency"] = text(invoice.get("currency"))
    row["paid_at"] = text(invoice.get("paid_at"))
    row["payment_status"] = text(invoice.get("payment_status"))
    row["sessions_count"] = config.SESSIONS_PER_TERM
    row["continue_same_batch"] = "Yes"
    row["match_method"] = "invoice"
    row["match_score"] = 1.0
    row["_state_since"] = invoice.get("paid_dt")

    reference = dataset.reference_by_student.get(text(invoice.get("student_id")))
    if reference:
        row["student_name"] = text(reference.get("student_name_masked"))
        row["educator_name"] = text(reference.get("educator_name"))
        row["classbatch_id"] = text(reference.get("current_classbatch_id"))
        row["preferred_days"] = text(reference.get("batch_days"))
        row["preferred_time"] = text(reference.get("batch_start_time"))

    if not payment_is_settled(invoice):
        return block(
            row,
            "R07",
            "Invoice {} is {} with no settled amount. Nothing can be scheduled yet.".format(
                invoice.get("invoice_number"), invoice.get("payment_status")
            ),
        )

    billed = invoice["amount_f"]
    collected = invoice["net_f"]
    expected = billed - invoice["discount_f"]
    tolerance = max(config.AMOUNT_TOLERANCE_ABS, billed * config.AMOUNT_TOLERANCE_PCT)
    if text(invoice.get("payment_type")).lower() != "full" or collected + tolerance < expected:
        return block(
            row,
            "R06",
            "Invoice {} billed {} and {} has been collected ({}). The fee is not settled, so a full 24 session term cannot be committed.".format(
                invoice.get("invoice_number"),
                format_money(billed),
                format_money(collected),
                invoice.get("payment_type"),
            ),
        )

    if not reference:
        return block(
            row,
            "R10",
            "Student {} has no row in the active batch reference, so there is no batch or teacher to schedule against.".format(
                invoice.get("student_id")
            ),
        )

    phone, email = identity_scores(invoice, reference)
    if phone < config.PHONE_MATCH_MIN and email < config.EMAIL_MATCH_MIN:
        return block(
            row,
            "R12",
            "Invoice {} was paid from {}, which matches neither the registered mobile ({}) nor the registered email ({}). No teacher form exists to corroborate the payer, so the payment is held until the contact is confirmed.".format(
                invoice.get("invoice_number"),
                invoice.get("mobile"),
                reference.get("registered_mobile_masked"),
                reference.get("registered_email_masked"),
            ),
        )
    if phone < config.PHONE_MATCH_MIN or email < config.EMAIL_MATCH_MIN:
        flag(row, "R12")

    if text(invoice.get("educator_id")) != text(reference.get("educator_id")):
        return block(
            row,
            "R13",
            "Invoice {} names teacher {} but the active record for student {} has teacher {}. One of the two is wrong.".format(
                invoice.get("invoice_number"),
                invoice.get("educator_id"),
                invoice.get("student_id"),
                reference.get("educator_id"),
            ),
        )

    if text(invoice.get("class_id")) != text(reference.get("class_id")):
        return block(
            row,
            "R14",
            "Invoice {} is for class {} but student {} is on class {} in the active record.".format(
                invoice.get("invoice_number"), invoice.get("class_id"), invoice.get("student_id"), reference.get("class_id")
            ),
        )

    batch_id = text(reference.get("current_classbatch_id"))
    batch = dataset.batches.get(batch_id)
    if not batch:
        return block(row, "R23", "Batch {} is not in the active reference, so no seat can be confirmed.".format(batch_id))

    country = phone_country(invoice.get("mobile"))
    if text(invoice.get("currency")).upper() != "INR" or (country and country != "IN"):
        flag(row, "R18")

    if invoice["discount_f"] > 0:
        flag(row, "R22")

    flag(row, "R01")
    reason = (
        "Payment {} cleared on {} against batch {} ({}). Phone, email, teacher and class match the active record. "
        "No teacher form was submitted and none is needed, because the payment carries every field this rule set uses."
    ).format(
        format_money(collected),
        format_date(invoice.get("paid_dt")),
        batch_id,
        text(batch.get("classbatch_name")),
    )
    return approve(row, reason)


def evaluate_form(form, match, dataset):
    invoice = match["invoice"]
    row = new_decision(text(invoice.get("id")), "form", text(form.get("id")), dataset)
    row["source"] = "faculty_form"
    row["evidence"] = "form + invoice"
    row["faculty_form_id"] = text(form.get("id"))
    row["invoice_id"] = text(invoice.get("id"))
    row["student_id"] = text(form.get("student_id"))
    row["student_name"] = text(form.get("student_name"))
    row["user_id"] = text(form.get("user_id"))
    row["class_id"] = text(form.get("class_id"))
    row["classbatch_id"] = text(form.get("current_classbatch_id"))
    row["educator_id"] = text(form.get("educator_id"))
    row["sessions_count"] = form["sessions_i"]
    row["continue_same_batch"] = "Yes" if form["continue_same_batch_b"] else "No"
    row["preferred_days"] = text(form.get("preferred_days"))
    row["preferred_time"] = text(form.get("preferred_time_slot"))
    row["amount_collected"] = invoice["net_f"]
    row["amount_claimed"] = form["amount_paid_f"]
    row["currency"] = text(invoice.get("currency"))
    row["paid_at"] = text(invoice.get("paid_at"))
    row["payment_status"] = text(invoice.get("payment_status"))
    row["match_method"] = match["method"]
    row["match_score"] = round(match["score"], 3)
    row["_state_since"] = invoice.get("paid_dt") or form.get("created_dt")

    reference = dataset.reference_by_student.get(text(invoice.get("student_id")))
    if reference:
        row["educator_name"] = text(reference.get("educator_name"))
        if not row["student_name"]:
            row["student_name"] = text(reference.get("student_name_masked"))

    if match["method"] == "fuzzy":
        flag(row, "R03")

    if not payment_is_settled(invoice):
        return block(
            row,
            "R07",
            "Invoice {} shows payment status {} with no settled amount, yet form {} was submitted as paid. The teacher likely saw a pending screen.".format(
                invoice.get("invoice_number"), invoice.get("payment_status"), form.get("id")
            ),
        )

    billed = invoice["amount_f"]
    collected = invoice["net_f"]
    claimed = form["amount_paid_f"]
    expected = billed - invoice["discount_f"]
    tolerance = max(config.AMOUNT_TOLERANCE_ABS, billed * config.AMOUNT_TOLERANCE_PCT)

    if text(invoice.get("payment_type")).lower() != "full" or collected + tolerance < expected:
        if abs(claimed - collected) > config.AMOUNT_TOLERANCE_ABS:
            flag(row, "R05")
        return block(
            row,
            "R06",
            "Invoice {} billed {} and {} has been collected ({}). Form {} claims {} was paid.".format(
                invoice.get("invoice_number"),
                format_money(billed),
                format_money(collected),
                invoice.get("payment_type"),
                form.get("id"),
                format_money(claimed),
            ),
        )

    if abs(claimed - collected) > config.AMOUNT_TOLERANCE_ABS:
        return block(
            row,
            "R05",
            "Form {} claims {} but invoice {} collected {}. Difference {}.".format(
                form.get("id"),
                format_money(claimed),
                invoice.get("invoice_number"),
                format_money(collected),
                format_money(abs(claimed - collected)),
            ),
        )

    if not reference:
        return block(
            row,
            "R10",
            "Student {} on form {} has no row in the active batch reference, so the batch and teacher cannot be verified.".format(
                form.get("student_id"), form.get("id")
            ),
        )

    phone, email = identity_scores(invoice, reference)
    payer_phone = phone_score(form.get("parent_mobile"), invoice.get("mobile"))
    form_phone = phone_score(form.get("parent_mobile"), reference.get("registered_mobile_masked"))

    if text(invoice.get("student_id")) != text(reference.get("student_id")) or text(form.get("student_id")) != text(invoice.get("student_id")):
        return block(
            row,
            "R11",
            "Form {} is for student {} but invoice {} belongs to student {}. The form and the payment describe different children.".format(
                form.get("id"), form.get("student_id"), invoice.get("invoice_number"), invoice.get("student_id")
            ),
        )

    if phone < config.PHONE_MATCH_MIN and email < config.EMAIL_MATCH_MIN:
        return block(
            row,
            "R12",
            "Invoice {} was paid from {}, which matches neither the registered mobile ({}) nor the registered email ({}). Form {} gives {}, which {} the registered number. Two minutes on the phone settles who paid before the class is released.".format(
                invoice.get("invoice_number"),
                invoice.get("mobile"),
                reference.get("registered_mobile_masked"),
                reference.get("registered_email_masked"),
                form.get("id"),
                form.get("parent_mobile"),
                "matches" if form_phone >= config.PHONE_MATCH_MIN else "also does not match",
            ),
        )

    if phone < config.PHONE_MATCH_MIN or email < config.EMAIL_MATCH_MIN or payer_phone < config.PHONE_MATCH_MIN:
        flag(row, "R12")

    batch_id = text(form.get("current_classbatch_id"))
    batch = dataset.batches.get(batch_id)

    if not form["continue_same_batch_b"]:
        requested_days = text(form.get("preferred_days")) or "not stated"
        requested_time = text(form.get("preferred_time_slot")) or "not stated"
        return block(
            row,
            "R09",
            "Teacher marked this as a batch change. Student {} sits in {} ({}) on {} at {}, and the form asks for {} at {}. A seat has to be found before anything is booked.".format(
                form.get("student_id"),
                batch_id,
                text(batch.get("classbatch_name")) if batch else "unknown batch",
                text(reference.get("batch_days")),
                text(reference.get("batch_start_time")),
                requested_days,
                requested_time,
            ),
        )

    if not batch:
        return block(
            row,
            "R23",
            "Batch {} on form {} is not in the active batch reference, so capacity and teacher cannot be checked.".format(
                batch_id, form.get("id")
            ),
        )

    if text(reference.get("current_classbatch_id")) != batch_id:
        return block(
            row,
            "R15",
            "Form {} names batch {} but student {} is on batch {} in the active record. The teacher is working from an old roster.".format(
                form.get("id"), batch_id, form.get("student_id"), reference.get("current_classbatch_id")
            ),
        )

    if text(form.get("educator_id")) != text(invoice.get("educator_id")):
        return block(
            row,
            "R13",
            "Form {} credits teacher {} but invoice {} was raised for teacher {}.".format(
                form.get("id"), form.get("educator_id"), invoice.get("invoice_number"), invoice.get("educator_id")
            ),
        )

    if text(form.get("educator_id")) != text(reference.get("educator_id")):
        return block(
            row,
            "R13",
            "Form {} credits teacher {} but the active record for student {} has teacher {}.".format(
                form.get("id"), form.get("educator_id"), form.get("student_id"), reference.get("educator_id")
            ),
        )

    if text(form.get("class_id")) != text(reference.get("class_id")):
        return block(
            row,
            "R14",
            "Form {} is for class {} but student {} is on class {} in the active record.".format(
                form.get("id"), form.get("class_id"), form.get("student_id"), reference.get("class_id")
            ),
        )

    if form["sessions_i"] <= 0:
        return block(
            row,
            "R16",
            "Form {} records {} sessions, which cannot be scheduled.".format(form.get("id"), form.get("sessions_i")),
        )
    if form["sessions_i"] != config.SESSIONS_PER_TERM:
        flag(row, "R16")

    country = phone_country(invoice.get("mobile"))
    if text(invoice.get("currency")).upper() != "INR" or (country and country != "IN"):
        flag(row, "R18")

    if abs(invoice["amount_f"] - reference["fee_f"]) > tolerance and invoice["discount_f"] <= 0:
        flag(row, "R19")

    if invoice["discount_f"] > 0:
        expected_net = invoice["amount_f"] - invoice["discount_f"]
        if abs(expected_net - collected) > config.AMOUNT_TOLERANCE_ABS:
            flag(row, "R19")
        flag(row, "R22")

    if not row["preferred_days"]:
        row["preferred_days"] = text(reference.get("batch_days"))
    if not row["preferred_time"]:
        row["preferred_time"] = text(reference.get("batch_start_time"))

    bookings = dataset.bookings_by_form.get(text(form.get("id")), [])
    sessions = []
    for booking in bookings:
        sessions.extend(dataset.schedule_by_booking.get(text(booking.get("id")), []))

    approval = text(form.get("approval_status")).lower()

    if approval == "approved":
        if not bookings:
            return block(
                row,
                "R21",
                "Form {} was approved on {} but no booking request exists for it, so no session was ever created.".format(
                    form.get("id"), text(form.get("approved_at"))
                ),
            )
        failed = [b for b in bookings if text(b.get("request_status")).lower().startswith("failed")]
        if not sessions:
            free = seats_available(dataset, batch_id)
            if failed and free is not None and free > 0:
                return block(
                    row,
                    "R08",
                    "Booking {} failed earlier with status {}, but batch {} now has {} seats free. The renewal can be recreated against the seat.".format(
                        failed[0].get("id"), failed[0].get("request_status"), batch_id, free
                    ),
                )
            if not failed:
                booking = bookings[0]
                row["_state_since"] = booking.get("created_dt") or form.get("created_dt")
                return block(
                    row,
                    "R20",
                    "Form {} was approved on {} and booking {} is still {}, {} after payment. Nobody created the sessions.".format(
                        form.get("id"),
                        text(form.get("approved_at")),
                        booking.get("id"),
                        booking.get("request_status"),
                        format_hours(age_hours(row, dataset)),
                    ),
                )
        if sessions:
            return finish_processed(row, form, sessions)

    if approval in {"rejected", "declined"}:
        return block(
            row,
            "R24",
            "Form {} was marked {} on {}. The renewal is not in the approval queue and will not be scheduled until it is fixed.".format(
                form.get("id"), text(form.get("approval_status")), text(form.get("updated_at"))
            ),
        )

    seats = seats_available(dataset, batch_id)
    reason = (
        "Payment {} cleared on {} against batch {} ({}). Form {} matches the invoice, the student, the teacher and the class. {} of {} seats in use."
    ).format(
        format_money(collected),
        format_date(invoice.get("paid_dt")),
        batch_id,
        text(batch.get("classbatch_name")),
        form.get("id"),
        to_int(batch.get("active_students_count")),
        to_int(batch.get("max_batch_size")),
    )
    if seats is not None and seats <= 0:
        reason = reason.replace("{} of {} seats in use.".format(
            to_int(batch.get("active_students_count")), to_int(batch.get("max_batch_size"))
        ), "Batch is at {} of {} seats.".format(
            to_int(batch.get("active_students_count")), to_int(batch.get("max_batch_size"))
        ))
    return approve(row, reason)


def finish_processed(row, form, sessions):
    row["decision"] = PROCESSED
    row["primary_code"] = "R17"
    row["severity"] = "Info"
    row["blocking"] = "No"
    row["owner"] = "system"
    row["sla_hours"] = 0
    row["recommended_action"] = CODES["R17"]["action"]
    row["reason"] = "Approved on {} and {} session rows already exist, first on {}. No action needed.".format(
        text(form.get("approved_at")),
        len(sessions),
        min(item["class_date"] for item in sessions if item.get("class_date")),
    )
    return row


def duplicate_decision(form, match, primary, dataset):
    invoice = match["invoice"]
    row = new_decision(primary["case_key"], "form", text(form.get("id")), dataset)
    row["record_role"] = "duplicate"
    row["source"] = "faculty_form"
    row["evidence"] = "form + invoice"
    row["faculty_form_id"] = text(form.get("id"))
    row["invoice_id"] = text(invoice.get("id"))
    row["student_id"] = text(form.get("student_id"))
    row["student_name"] = text(form.get("student_name"))
    row["user_id"] = text(form.get("user_id"))
    row["class_id"] = text(form.get("class_id"))
    row["classbatch_id"] = text(form.get("current_classbatch_id"))
    row["educator_id"] = text(form.get("educator_id"))
    row["amount_collected"] = invoice["net_f"]
    row["amount_claimed"] = form["amount_paid_f"]
    row["currency"] = text(invoice.get("currency"))
    row["paid_at"] = text(invoice.get("paid_at"))
    row["payment_status"] = text(invoice.get("payment_status"))
    row["match_method"] = match["method"]
    row["match_score"] = round(match["score"], 3)
    row["_state_since"] = form.get("created_dt")
    reference = dataset.reference_by_student.get(text(invoice.get("student_id")))
    if reference:
        row["educator_name"] = text(reference.get("educator_name"))

    first = dataset.forms_by_id.get(primary["record_id"])
    gap_minutes = 0
    if first and first.get("created_dt") and form.get("created_dt"):
        gap_minutes = int(round((form["created_dt"] - first["created_dt"]).total_seconds() / 60.0))

    block(
        row,
        "R04",
        "Form {} repeats invoice {} {} minutes after form {}. Same student, same amount, so this is one renewal submitted twice.".format(
            form.get("id"), invoice.get("invoice_number"), gap_minutes, primary["record_id"]
        ),
    )
    row["blocking"] = "No"
    row["severity"] = "Low"
    return row


def unresolved_decision(form, match, dataset):
    case_key = "FORM-{}".format(form.get("id"))
    row = new_decision(case_key, "form", text(form.get("id")), dataset)
    row["source"] = "faculty_form"
    row["evidence"] = "form only"
    row["faculty_form_id"] = text(form.get("id"))
    row["student_id"] = text(form.get("student_id"))
    row["student_name"] = text(form.get("student_name"))
    row["user_id"] = text(form.get("user_id"))
    row["class_id"] = text(form.get("class_id"))
    row["classbatch_id"] = text(form.get("current_classbatch_id"))
    row["educator_id"] = text(form.get("educator_id"))
    row["amount_claimed"] = form["amount_paid_f"]
    row["payment_status"] = "unknown"
    row["match_method"] = match["method"]
    row["match_score"] = round(match.get("score", 0.0), 3)
    row["_state_since"] = form.get("created_dt")
    reference = dataset.reference_by_student.get(text(form.get("student_id")))
    if reference:
        row["educator_name"] = text(reference.get("educator_name"))

    claimed = match.get("claimed_id") or form.get("invoice_id")
    linked = match.get("link_id") or "no link"

    if match["conflict"]:
        reason = (
            "Form {} names invoice {} but its link points to {}. Both invoices exist in the table, so there is no safe way to tell which payment this renewal belongs to."
        ).format(form.get("id"), claimed, linked)
    elif match["method"] == "ambiguous":
        reason = (
            "Form {} points at invoice {} and link {}, and {} candidate invoices fit the student and amount within {} of each other. No repair attempted because the second best match is too close."
        ).format(form.get("id"), claimed, linked, 2, match.get("runner_up"))
    elif match["method"] == "below_threshold":
        reason = (
            "Form {} points at invoice {} and link {}. The closest invoice for this student and amount scores {:.2f}, below the {:.2f} repair threshold, so it was not accepted."
        ).format(form.get("id"), claimed, linked, match.get("score", 0.0), config.INVOICE_SIMILARITY_MIN)
    else:
        reason = (
            "Form {} points at invoice {} and link {}. No invoice exists with that number and no invoice for student {} matches {} closely enough to repair it."
        ).format(form.get("id"), claimed, linked, form.get("student_id"), format_money(form.get("amount_paid")))

    return block(row, "R02", reason)


def allocate_seats(decisions, dataset):
    ledger = {}
    ordered = sorted(
        decisions,
        key=lambda row: (int(row["case_key"]) if row["case_key"].isdigit() else 0, row["record_type"], row["record_id"]),
    )
    for row in ordered:
        if row["decision"] != AUTO:
            continue
        batch_id = text(row["classbatch_id"])
        batch = dataset.batches.get(batch_id)
        if not batch:
            block(row, "R23", "Batch {} is not in the active reference, so no seat can be confirmed.".format(batch_id))
            continue
        if batch_id not in ledger:
            ledger[batch_id] = to_int(batch.get("active_students_count"))
        seats_left = to_int(batch.get("max_batch_size")) - ledger[batch_id]
        if seats_left <= 0:
            same_batch = text(row["classbatch_id"]) == text(
                dataset.reference_by_student.get(row["student_id"], {}).get("current_classbatch_id")
            )
            note = ""
            if same_batch:
                note = " The student is already counted inside those {} seats, so confirm whether this is a real capacity block or a counting artefact.".format(
                    to_int(batch.get("max_batch_size"))
                )
            block(
                row,
                "R08",
                "Batch {} ({}) is at {} of {} seats. {} cleared {} ago and cannot be seated until a seat frees up or the teacher confirms the batch continues.{}".format(
                    batch_id,
                    text(batch.get("classbatch_name")),
                    to_int(batch.get("active_students_count")),
                    to_int(batch.get("max_batch_size")),
                    format_money(row["amount_collected"]),
                    format_hours(age_hours(row, dataset)),
                    note,
                ),
            )
            continue
        ledger[batch_id] += 1
        row["seats_left_after"] = seats_left - 1


def finalize(decisions, dataset):
    for row in decisions:
        since = row.pop("_state_since", None)
        if since:
            row["hours_in_state"] = round(max(0.0, (dataset.as_of - since).total_seconds() / 3600.0), 1)
        else:
            row["hours_in_state"] = 0.0
        codes = set(row["flags"])
        codes.discard(row["primary_code"])
        row["flags"] = ",".join(sorted(codes))
        row["secondary_codes"] = row["flags"]
    return decisions


def evaluate(dataset):
    matches = {}
    for form in dataset.forms:
        matches[form["id"]] = resolve_invoice(form, dataset.invoices_by_id, dataset.invoices)

    forms_by_invoice = {}
    unresolved = []
    blocked_invoices = set()
    for form in dataset.forms:
        match = matches[form["id"]]
        invoice = match["invoice"]
        if invoice is None:
            unresolved.append(form)
            continue
        if match["conflict"]:
            unresolved.append(form)
            blocked_invoices.add(text(invoice.get("id")))
            continue
        forms_by_invoice.setdefault(text(invoice.get("id")), []).append(form)

    decisions = []
    for invoice in dataset.invoices:
        invoice_id = text(invoice.get("id"))
        invoice_forms = forms_by_invoice.get(invoice_id, [])
        if not invoice_forms:
            if invoice_id in blocked_invoices:
                continue
            decisions.append(evaluate_invoice_only(invoice, dataset))
            continue
        primary_form = invoice_forms[0]
        primary = evaluate_form(primary_form, matches[primary_form["id"]], dataset)
        decisions.append(primary)
        for duplicate in invoice_forms[1:]:
            decisions.append(duplicate_decision(duplicate, matches[duplicate["id"]], primary, dataset))

    for form in unresolved:
        decisions.append(unresolved_decision(form, matches[form["id"]], dataset))

    allocate_seats(decisions, dataset)
    finalize(decisions, dataset)

    return sorted(
        decisions,
        key=lambda row: (
            int(row["case_key"]) if row["case_key"].isdigit() else 999999,
            row["case_key"],
            row["record_type"],
            row["record_id"],
        ),
    )
