from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
PROMPT_DIR = ROOT / "prompts"
ASSUMPTIONS_FILE = Path(__file__).resolve().parent / "savings_assumptions.json"

INVOICE_FILE = "1_invoices.csv"
FORM_FILE = "2_faculty_form_unapproved.csv"
BOOKING_FILE = "3_booking_requests.csv"
SCHEDULE_FILE = "4_class_schedule_bookings.csv"
REFERENCE_FILE = "reference_active_batches_and_students.csv"

ENGINE_VERSION = "1.1.0"

INVOICE_SIMILARITY_MIN = 0.72
INVOICE_MARGIN_MIN = 0.05
PHONE_MATCH_MIN = 0.80
EMAIL_MATCH_MIN = 0.80
AMOUNT_TOLERANCE_ABS = 1.0
AMOUNT_TOLERANCE_PCT = 0.005

STUCK_INVOICE_HOURS = 12
ESCALATION_HOURS = 24
SESSIONS_PER_TERM = 24

OPENAI_MODEL = "gpt-4.1-mini"
