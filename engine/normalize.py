import re
from datetime import datetime
from difflib import SequenceMatcher

NULLS = {"", "NULL", "null", "None", "NA", "N/A", "-"}


def text(value):
    if value is None:
        return ""
    return str(value).strip()


def is_yes(value):
    return text(value).lower() in {"yes", "y", "true", "1"}


def to_float(value, default=0.0):
    raw = text(value).replace(",", "").replace("INR", "").replace("Rs", "").strip()
    if raw in NULLS:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def to_int(value, default=0):
    raw = text(value)
    if raw in NULLS:
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def to_dt(value):
    raw = text(value)
    if raw in NULLS:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def similarity(left, right):
    first = text(left).lower()
    second = text(right).lower()
    if not first or not second:
        return 0.0
    return SequenceMatcher(None, first, second).ratio()


def phone_digits(value):
    stripped = re.sub(r"[^0-9X]", "", text(value).upper())
    if stripped.startswith("00"):
        stripped = stripped[2:]
    return stripped


def normalize_phone(value):
    digits = phone_digits(value)
    if digits.startswith("971") and len(digits) >= 12:
        return digits[3:]
    if digits.startswith("1") and len(digits) == 11:
        return digits[1:]
    if digits.startswith("0") and len(digits) > 10:
        digits = digits[1:]
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    return digits


def phone_country(value):
    digits = phone_digits(value)
    if digits.startswith("971"):
        return "AE"
    if digits.startswith("1") and len(digits) >= 11:
        return "US"
    if digits.startswith("91"):
        return "IN"
    return ""


def phone_score(left, right):
    first = normalize_phone(left)
    second = normalize_phone(right)
    if not first or not second:
        return 0.0
    if first == second:
        return 1.0
    tail = min(len(first), len(second), 6)
    if tail >= 4 and first[-tail:] == second[-tail:]:
        return 0.8
    return 0.0


def normalize_email(value):
    return text(value).lower()


def email_score(left, right):
    first = normalize_email(left)
    second = normalize_email(right)
    if not first or not second:
        return 0.0
    if first == second:
        return 1.0
    local_first, _, domain_first = first.partition("@")
    local_second, _, domain_second = second.partition("@")
    if not domain_first or domain_first != domain_second:
        return 0.0
    if local_first[:2] and local_first[:2] == local_second[:2]:
        return 0.7
    return 0.0


def name_score(left, right):
    first = text(left)
    second = text(right)
    if not first or not second:
        return 0.0
    if first.lower() == second.lower():
        return 1.0
    tokens_first = first.split()
    tokens_second = second.split()
    if not tokens_first or not tokens_second:
        return 0.0
    score = similarity(tokens_first[-1], tokens_second[-1]) * 0.45
    prefix_first = tokens_first[0].split("***")[0]
    prefix_second = tokens_second[0].split("***")[0]
    if prefix_first and prefix_first.lower() == prefix_second.lower():
        score += 0.45
    return round(min(score, 1.0), 3)


def parse_invoice_ref(value):
    raw = text(value)
    if not raw:
        return ""
    runs = re.findall(r"\d+", raw)
    if not runs:
        return ""
    return runs[-1]


def hours_between(start, end):
    if not start or not end:
        return None
    return round((end - start).total_seconds() / 3600.0, 2)


def format_money(value):
    amount = to_float(value)
    if abs(amount - round(amount)) < 0.01:
        return "INR {:,}".format(int(round(amount)))
    return "INR {:,.2f}".format(amount)


def format_hours(value):
    hours = to_float(value)
    if hours < 1:
        return "{} minutes".format(int(round(hours * 60)))
    if hours < 48:
        return "{:.1f} hours".format(hours)
    return "{:.1f} days".format(hours / 24.0)


def format_date(value):
    parsed = value if isinstance(value, datetime) else to_dt(value)
    if not parsed:
        return ""
    return "{} {}".format(parsed.day, parsed.strftime("%b"))
