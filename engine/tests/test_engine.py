import csv
import shutil
from pathlib import Path

import pytest

from engine.load import load_dataset
from engine.normalize import email_score, normalize_phone, parse_invoice_ref, phone_score
from engine.pipeline import run
from engine.rules import evaluate

DATA = Path(__file__).resolve().parents[2] / "data"
FILES = [
    "1_invoices.csv",
    "2_faculty_form_unapproved.csv",
    "3_booking_requests.csv",
    "4_class_schedule_bookings.csv",
    "reference_active_batches_and_students.csv",
]


def copy_data(tmp_path):
    for name in FILES:
        shutil.copy(DATA / name, tmp_path / name)
    return tmp_path


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def edit_row(tmp_path, filename, row_id, **changes):
    path = tmp_path / filename
    rows = read_csv(path)
    found = False
    for row in rows:
        if row["id"] == row_id:
            row.update({key: str(value) for key, value in changes.items()})
            found = True
    if not found:
        raise AssertionError("row {} not found in {}".format(row_id, filename))
    write_csv(path, rows)


def remove_row(tmp_path, filename, row_id):
    path = tmp_path / filename
    rows = [row for row in read_csv(path) if row["id"] != row_id]
    write_csv(path, rows)


def edit_reference(tmp_path, student_id, **changes):
    path = tmp_path / "reference_active_batches_and_students.csv"
    rows = read_csv(path)
    for row in rows:
        if row["student_id"] == student_id:
            row.update({key: str(value) for key, value in changes.items()})
    write_csv(path, rows)


def remove_reference(tmp_path, student_id):
    path = tmp_path / "reference_active_batches_and_students.csv"
    rows = [row for row in read_csv(path) if row["student_id"] != student_id]
    write_csv(path, rows)


def decisions_for(tmp_path):
    return evaluate(load_dataset(tmp_path))


def case(decisions, case_key):
    for row in decisions:
        if row["case_key"] == case_key and row["record_role"] == "primary":
            return row
    raise AssertionError("case {} not found".format(case_key))


def record(decisions, record_id):
    for row in decisions:
        if row["record_id"] == record_id:
            return row
    raise AssertionError("record {} not found".format(record_id))


def test_r00_clean_renewal_is_auto_approved(tmp_path):
    decisions = decisions_for(copy_data(tmp_path))
    row = case(decisions, "84903")
    assert row["primary_code"] == "R00"
    assert row["decision"] == "AUTO_APPROVE"
    assert row["flags"] == ""


def test_r01_paid_invoice_without_a_form_is_still_scheduled(tmp_path):
    decisions = decisions_for(copy_data(tmp_path))
    row = case(decisions, "84906")
    assert row["decision"] == "AUTO_APPROVE"
    assert "R01" in row["flags"]
    assert row["evidence"] == "invoice only"
    assert row["classbatch_id"] == "9206"


def test_r02_unresolvable_invoice_reference_blocks(tmp_path):
    data = copy_data(tmp_path)
    edit_row(
        data,
        "2_faculty_form_unapproved.csv",
        "3313",
        invoice_id="77777",
        invoice_link="https://bambinos.live/invoice/BMB-INV-2026-77777",
    )
    decisions = decisions_for(data)
    row = record(decisions, "3313")
    assert row["primary_code"] == "R02"
    assert row["owner"] == "teacher"
    assert row["blocking"] == "Yes"


def test_r03_typo_in_invoice_link_is_repaired(tmp_path):
    decisions = decisions_for(copy_data(tmp_path))
    row = case(decisions, "84913")
    assert row["match_method"] == "fuzzy"
    assert "R03" in row["flags"]
    assert row["decision"] == "AUTO_APPROVE"


def test_r04_duplicate_form_is_closed_not_rescheduled(tmp_path):
    decisions = decisions_for(copy_data(tmp_path))
    duplicate = record(decisions, "3309")
    assert duplicate["primary_code"] == "R04"
    assert duplicate["blocking"] == "No"
    assert duplicate["record_role"] == "duplicate"


def test_r05_claimed_amount_mismatch_blocks(tmp_path):
    data = copy_data(tmp_path)
    edit_row(data, "2_faculty_form_unapproved.csv", "3303", amount_paid="7500.00")
    decisions = decisions_for(data)
    row = case(decisions, "84903")
    assert row["primary_code"] == "R05"
    assert row["owner"] == "finance"


def test_r06_partial_payment_blocks(tmp_path):
    decisions = decisions_for(copy_data(tmp_path))
    row = case(decisions, "84909")
    assert row["primary_code"] == "R06"
    assert "R05" in row["secondary_codes"]


def test_r07_failed_payment_blocks(tmp_path):
    decisions = decisions_for(copy_data(tmp_path))
    row = case(decisions, "84911")
    assert row["primary_code"] == "R07"
    assert row["owner"] == "parent"


def test_r08_full_batch_blocks_with_capacity_detail(tmp_path):
    decisions = decisions_for(copy_data(tmp_path))
    row = case(decisions, "84905")
    assert row["primary_code"] == "R08"
    assert "6 of 6" in row["reason"]


def test_r09_batch_change_waits_for_parent(tmp_path):
    decisions = decisions_for(copy_data(tmp_path))
    row = case(decisions, "84912")
    assert row["primary_code"] == "R09"
    assert row["owner"] == "parent"


def test_r10_student_missing_from_reference(tmp_path):
    data = copy_data(tmp_path)
    remove_reference(data, "68103")
    decisions = decisions_for(data)
    row = case(decisions, "84903")
    assert row["primary_code"] == "R10"


def test_r11_form_and_invoice_name_different_students(tmp_path):
    data = copy_data(tmp_path)
    edit_row(data, "2_faculty_form_unapproved.csv", "3303", student_id="68999")
    decisions = decisions_for(data)
    row = case(decisions, "84903")
    assert row["primary_code"] == "R11"
    assert row["blocking"] == "Yes"


def test_r12_payer_contact_mismatch_holds_for_verification(tmp_path):
    decisions = decisions_for(copy_data(tmp_path))
    row = case(decisions, "84904")
    assert row["primary_code"] == "R12"
    assert row["owner"] == "ops_agent"
    assert "XXXX77" in row["reason"]


def test_r13_educator_mismatch_blocks(tmp_path):
    data = copy_data(tmp_path)
    edit_row(data, "1_invoices.csv", "84903", educator_id="9999")
    decisions = decisions_for(data)
    row = case(decisions, "84903")
    assert row["primary_code"] == "R13"


def test_r14_class_mismatch_blocks(tmp_path):
    data = copy_data(tmp_path)
    edit_row(data, "2_faculty_form_unapproved.csv", "3303", class_id="999")
    decisions = decisions_for(data)
    row = case(decisions, "84903")
    assert row["primary_code"] == "R14"


def test_r15_stale_batch_on_form(tmp_path):
    data = copy_data(tmp_path)
    edit_reference(data, "68103", current_classbatch_id="9299")
    decisions = decisions_for(data)
    row = case(decisions, "84903")
    assert row["primary_code"] == "R15"


def test_r16_zero_sessions_blocks(tmp_path):
    data = copy_data(tmp_path)
    edit_row(data, "2_faculty_form_unapproved.csv", "3303", sessions_purchased="0")
    decisions = decisions_for(data)
    row = case(decisions, "84903")
    assert row["primary_code"] == "R16"


def test_r17_scheduled_case_is_not_touched_again(tmp_path):
    decisions = decisions_for(copy_data(tmp_path))
    row = case(decisions, "84901")
    assert row["primary_code"] == "R17"
    assert row["decision"] == "ALREADY_PROCESSED"


def test_r18_cross_border_payment_is_flagged(tmp_path):
    decisions = decisions_for(copy_data(tmp_path))
    row = case(decisions, "84906")
    assert "R18" in row["flags"]


def test_r19_fee_variance_is_flagged(tmp_path):
    data = copy_data(tmp_path)
    edit_row(data, "1_invoices.csv", "84903", amount="11000.00", net_amount="11000.00")
    edit_row(data, "2_faculty_form_unapproved.csv", "3303", amount_paid="11000.00")
    decisions = decisions_for(data)
    row = case(decisions, "84903")
    assert "R19" in row["flags"]
    assert row["decision"] == "AUTO_APPROVE"


def test_r20_approved_but_never_scheduled(tmp_path):
    decisions = decisions_for(copy_data(tmp_path))
    row = case(decisions, "84902")
    assert row["primary_code"] == "R20"
    assert row["owner"] == "ops_agent"


def test_r21_approved_form_without_booking(tmp_path):
    data = copy_data(tmp_path)
    remove_row(data, "3_booking_requests.csv", "5501")
    decisions = decisions_for(data)
    row = case(decisions, "84901")
    assert row["primary_code"] == "R21"


def test_r22_discount_is_flagged_but_not_blocked(tmp_path):
    decisions = decisions_for(copy_data(tmp_path))
    row = case(decisions, "84907")
    assert "R22" in row["flags"]
    assert row["decision"] == "AUTO_APPROVE"


def test_r23_batch_missing_from_reference(tmp_path):
    data = copy_data(tmp_path)
    edit_row(data, "2_faculty_form_unapproved.csv", "3303", current_classbatch_id="9999")
    decisions = decisions_for(data)
    row = case(decisions, "84903")
    assert row["primary_code"] == "R23"


def test_r24_rejected_form_is_not_scheduled(tmp_path):
    data = copy_data(tmp_path)
    edit_row(data, "2_faculty_form_unapproved.csv", "3303", approval_status="Rejected")
    decisions = decisions_for(data)
    row = case(decisions, "84903")
    assert row["primary_code"] == "R24"


def test_run_writes_every_required_output(tmp_path):
    summary = run(copy_data(tmp_path), tmp_path / "out")
    out = tmp_path / "out"
    for name in ("auto_approved.csv", "exceptions.csv", "messages.csv", "messages.md", "summary.json"):
        assert (out / name).exists(), name
    assert summary["cases"]["total"] == 13
    assert summary["auto_approved"] == 6
    assert summary["exceptions_blocking"] == 6
    assert summary["metrics"]["orphaned_invoices"] == 2
    assert summary["estimated_hours_saved_per_month"] > 0


def test_run_is_idempotent(tmp_path):
    data = copy_data(tmp_path)
    run(data, tmp_path / "first")
    run(data, tmp_path / "second")
    for name in ("auto_approved.csv", "exceptions.csv", "messages.csv", "summary.json"):
        assert (tmp_path / "first" / name).read_bytes() == (tmp_path / "second" / name).read_bytes(), name


def test_every_exception_has_an_owner_sla_and_message(tmp_path):
    run(copy_data(tmp_path), tmp_path / "out")
    exceptions = read_csv(tmp_path / "out" / "exceptions.csv")
    messages = read_csv(tmp_path / "out" / "messages.csv")
    covered = {row["case_key"] for row in messages}
    for row in exceptions:
        assert row["owner"]
        assert int(row["sla_hours"]) >= 0
        assert row["recommended_action"]
        assert row["reason"]
        if row["blocking"] == "Yes":
            assert row["case_key"] in covered
    for row in messages:
        assert row["recipient"]
        assert len(row["message"]) > 40


def test_phone_normalization_handles_country_codes():
    assert normalize_phone("+91 98110 00001") == normalize_phone("09811000001")
    assert normalize_phone("+91 98110 00001") == normalize_phone("919811000001")
    assert normalize_phone("+971 50 123 4567") == "501234567"
    assert phone_score("+91-9811XXXX01", "+91-9811XXXX01") == 1.0


def test_email_and_reference_parsing():
    assert email_score("a.b@example.com", "A.B@example.com") == 1.0
    assert email_score("a.b@gmail.com", "a.b@outlook.com") == 0.0
    assert parse_invoice_ref("https://bambinos.live/invoice/BMB-INV-2026-84913") == "84913"
    assert parse_invoice_ref("BMB-INV-2026-84931") == "84931"


def test_fuzzy_repair_refuses_two_equal_candidates(tmp_path):
    data = copy_data(tmp_path)
    rows = read_csv(data / "1_invoices.csv")
    clone = dict(rows[-1])
    clone["id"] = "84914"
    clone["invoice_number"] = "BMB-INV-2026-84914"
    clone["invoice_link"] = "https://bambinos.live/invoice/BMB-INV-2026-84914"
    rows.append(clone)
    write_csv(data / "1_invoices.csv", rows)
    decisions = decisions_for(data)
    row = record(decisions, "3313")
    assert row["primary_code"] == "R02"
    assert row["match_method"] == "ambiguous"
