import json
from statistics import mean

from . import config

DEFAULTS = {
    "monthly_renewals": 1000,
    "ops_hourly_cost_inr": 300.0,
    "one_time_build_cost_inr": 200000.0,
    "auto_approval_rate_low": 0.55,
    "auto_approval_rate_base": 0.70,
    "auto_approval_rate_high": 0.80,
    "context_switch_allowance_pct": 0.25,
    "automation_overhead_pct": 0.10,
    "manual_minutes": {
        "R00": 7.0,
        "R01": 11.0,
        "R02": 9.0,
        "R04": 1.5,
        "R05": 12.0,
        "R06": 12.0,
        "R07": 12.0,
        "R08": 15.0,
        "R09": 14.0,
        "R10": 12.0,
        "R11": 10.0,
        "R12": 8.0,
        "R13": 9.0,
        "R14": 9.0,
        "R15": 8.0,
        "R16": 8.5,
        "R17": 0.5,
        "R18": 8.0,
        "R19": 11.0,
        "R20": 6.0,
        "R21": 6.0,
        "R22": 7.0,
        "R23": 8.0,
        "R24": 8.0,
    },
    "new_minutes": {
        "R00": 0.25,
        "R01": 0.25,
        "R02": 3.0,
        "R04": 0.5,
        "R05": 3.0,
        "R06": 4.0,
        "R07": 4.0,
        "R08": 5.0,
        "R09": 6.0,
        "R10": 5.0,
        "R11": 5.0,
        "R12": 0.5,
        "R13": 3.0,
        "R14": 3.0,
        "R15": 3.0,
        "R16": 3.0,
        "R17": 0.0,
        "R18": 0.25,
        "R19": 2.0,
        "R20": 1.0,
        "R21": 1.0,
        "R22": 0.25,
        "R23": 3.0,
        "R24": 3.0,
    },
}


def load_assumptions(path=None):
    settings = json.loads(json.dumps(DEFAULTS))
    target = path or config.ASSUMPTIONS_FILE
    if not target.exists():
        return settings
    with open(target, encoding="utf-8") as handle:
        overrides = json.load(handle)
    for key, value in overrides.items():
        if key in ("manual_minutes", "new_minutes") and isinstance(value, dict):
            settings[key].update({code: float(minutes) for code, minutes in value.items()})
        elif key in settings:
            settings[key] = value
    return settings


def scenario(settings, decisions, rate):
    manual = settings["manual_minutes"]
    new = settings["new_minutes"]
    codes = [row["primary_code"] for row in decisions if row["record_role"] == "primary"]
    manual_mean = mean(manual.get(code, manual["R00"]) for code in codes)
    exception_codes = [code for code in codes if code not in ("R00", "R01", "R17")]
    exception_new_mean = mean(new.get(code, 4.0) for code in exception_codes) if exception_codes else 0.0
    today_minutes = manual_mean * (1 + settings["context_switch_allowance_pct"])
    new_minutes = rate * new["R00"] * (1 + settings["automation_overhead_pct"]) + (1 - rate) * exception_new_mean
    monthly = settings["monthly_renewals"]
    hours_today = monthly * today_minutes / 60.0
    hours_new = monthly * new_minutes / 60.0
    hours_saved = hours_today - hours_new
    cost_today = hours_today * settings["ops_hourly_cost_inr"]
    cost_new = hours_new * settings["ops_hourly_cost_inr"]
    cost_saved = cost_today - cost_new
    payback = settings["one_time_build_cost_inr"] / cost_saved if cost_saved > 0 else None
    return {
        "auto_approval_rate": rate,
        "manual_mean_minutes": round(manual_mean, 2),
        "today_minutes_per_case": round(today_minutes, 2),
        "new_minutes_per_case": round(new_minutes, 2),
        "exception_new_minutes": round(exception_new_mean, 2),
        "hours_today_per_month": round(hours_today, 1),
        "hours_new_per_month": round(hours_new, 1),
        "hours_saved_per_month": round(hours_saved, 1),
        "hours_saved_per_year": round(hours_saved * 12, 0),
        "cost_today_per_month_inr": round(cost_today),
        "cost_new_per_month_inr": round(cost_new),
        "cost_saved_per_month_inr": round(cost_saved),
        "cost_saved_per_year_inr": round(cost_saved * 12),
        "payback_months": round(payback, 1) if payback else None,
    }


def build_savings(decisions, settings=None):
    active = settings or load_assumptions()
    low = scenario(active, decisions, active["auto_approval_rate_low"])
    base = scenario(active, decisions, active["auto_approval_rate_base"])
    high = scenario(active, decisions, active["auto_approval_rate_high"])
    codes = [row["primary_code"] for row in decisions if row["record_role"] == "primary"]
    counts = {}
    for code in codes:
        counts[code] = counts.get(code, 0) + 1
    return {
        "assumptions": {
            "monthly_renewals": active["monthly_renewals"],
            "ops_hourly_cost_inr": active["ops_hourly_cost_inr"],
            "one_time_build_cost_inr": active["one_time_build_cost_inr"],
            "context_switch_allowance_pct": active["context_switch_allowance_pct"],
            "automation_overhead_pct": active["automation_overhead_pct"],
            "source": "engine/savings_assumptions.json",
        },
        "observed_case_mix": counts,
        "scenarios": {"low": low, "base": base, "high": high},
        "base": base,
    }
