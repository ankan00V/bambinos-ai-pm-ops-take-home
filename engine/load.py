import csv
from pathlib import Path

from . import config
from .normalize import is_yes, text, to_dt, to_float, to_int

TIMESTAMP_FIELDS = (
    "paid_at",
    "created_at",
    "updated_at",
    "approved_at",
    "allocated_at",
    "deleted_at",
)


def read_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            clean = {}
            for key, value in row.items():
                if key is None:
                    continue
                clean[key.strip()] = text(value)
            rows.append(clean)
        return rows


def prepare_invoice(row):
    row["amount_f"] = to_float(row.get("amount"))
    row["discount_f"] = to_float(row.get("discount_amount"))
    row["net_f"] = to_float(row.get("net_amount"))
    row["paid_dt"] = to_dt(row.get("paid_at"))
    row["created_dt"] = to_dt(row.get("created_at"))
    row["updated_dt"] = to_dt(row.get("updated_at"))
    return row


def prepare_form(row):
    row["amount_paid_f"] = to_float(row.get("amount_paid"))
    row["sessions_i"] = to_int(row.get("sessions_purchased"))
    row["created_dt"] = to_dt(row.get("created_at"))
    row["approved_dt"] = to_dt(row.get("approved_at"))
    row["updated_dt"] = to_dt(row.get("updated_at"))
    row["continue_same_batch_b"] = is_yes(row.get("continue_same_batch"))
    return row


def prepare_booking(row):
    row["sessions_i"] = to_int(row.get("sessions_count"))
    row["created_dt"] = to_dt(row.get("created_at"))
    row["allocated_dt"] = to_dt(row.get("allocated_at"))
    row["continue_same_batch_b"] = is_yes(row.get("continue_same_batch"))
    return row


def prepare_schedule(row):
    row["created_dt"] = to_dt(row.get("created_at"))
    row["class_day"] = to_dt(row.get("class_date"))
    row["start_dt"] = to_dt("{} {}".format(row.get("class_date"), row.get("start_time")))
    return row


def prepare_reference(row):
    row["fee_f"] = to_float(row.get("standard_fee_24_sessions_inr"))
    row["active_i"] = to_int(row.get("active_students_count"))
    row["max_i"] = to_int(row.get("max_batch_size"))
    return row


def latest_timestamp(tables):
    latest = None
    for rows in tables:
        for row in rows:
            for field in TIMESTAMP_FIELDS:
                value = to_dt(row.get(field))
                if value and (latest is None or value > latest):
                    latest = value
    return latest


class Dataset:
    def __init__(self, invoices, forms, bookings, schedule, reference, as_of):
        self.invoices = sorted(invoices, key=lambda row: text(row.get("id")))
        self.forms = sorted(forms, key=lambda row: (row.get("created_at", ""), text(row.get("id"))))
        self.bookings = sorted(bookings, key=lambda row: text(row.get("id")))
        self.schedule = sorted(schedule, key=lambda row: text(row.get("id")))
        self.reference = reference
        self.as_of = as_of

        self.invoices_by_id = {text(row.get("id")): row for row in self.invoices}
        self.forms_by_id = {text(row.get("id")): row for row in self.forms}
        self.bookings_by_form = {}
        self.bookings_by_invoice = {}
        for row in self.bookings:
            self.bookings_by_form.setdefault(text(row.get("faculty_form_id")), []).append(row)
            self.bookings_by_invoice.setdefault(text(row.get("invoice_id")), []).append(row)

        self.schedule_by_booking = {}
        self.schedule_by_invoice = {}
        for row in self.schedule:
            self.schedule_by_booking.setdefault(text(row.get("bookingrequest_id")), []).append(row)
            self.schedule_by_invoice.setdefault(text(row.get("invoice_id")), []).append(row)

        self.reference_by_student = {}
        self.batches = {}
        for row in reference:
            self.reference_by_student[text(row.get("student_id"))] = row
            self.batches.setdefault(text(row.get("current_classbatch_id")), row)

    def batch_of(self, student_id):
        row = self.reference_by_student.get(text(student_id))
        if not row:
            return None
        return self.batches.get(text(row.get("current_classbatch_id")))

    def future_sessions(self, invoice_id):
        count = 0
        for row in self.schedule_by_invoice.get(text(invoice_id), []):
            if text(row.get("is_cancelled")).lower() == "yes":
                continue
            day = row.get("class_day")
            if day and day >= self.as_of:
                count += 1
        return count


def load_dataset(data_dir=None):
    base = Path(data_dir) if data_dir else config.DATA_DIR
    invoices = [prepare_invoice(row) for row in read_rows(base / config.INVOICE_FILE)]
    forms = [prepare_form(row) for row in read_rows(base / config.FORM_FILE)]
    bookings = [prepare_booking(row) for row in read_rows(base / config.BOOKING_FILE)]
    schedule = [prepare_schedule(row) for row in read_rows(base / config.SCHEDULE_FILE)]
    reference = [prepare_reference(row) for row in read_rows(base / config.REFERENCE_FILE)]

    as_of = latest_timestamp([invoices, forms, bookings, schedule, reference])
    return Dataset(invoices, forms, bookings, schedule, reference, as_of)
