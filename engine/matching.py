from . import config
from .normalize import parse_invoice_ref, similarity, text, to_float


def amount_matches(claimed, invoice):
    net = invoice["net_f"]
    tolerance = max(config.AMOUNT_TOLERANCE_ABS, net * config.AMOUNT_TOLERANCE_PCT)
    return abs(to_float(claimed) - net) <= tolerance


def empty_match(method, claimed_id, link_id, score=0.0, runner_up=0.0):
    return {
        "invoice": None,
        "method": method,
        "score": score,
        "runner_up": runner_up,
        "claimed_id": claimed_id,
        "link_id": link_id,
        "conflict": False,
    }


def resolve_invoice(form, invoices_by_id, invoice_list):
    claimed_id = text(form.get("invoice_id"))
    link = text(form.get("invoice_link"))
    link_id = parse_invoice_ref(link)
    claimed_invoice = invoices_by_id.get(claimed_id)
    link_invoice = invoices_by_id.get(link_id)

    if claimed_invoice and link_invoice and claimed_id != link_id:
        match = {
            "invoice": claimed_invoice,
            "method": "conflict",
            "score": 1.0,
            "runner_up": 1.0,
            "claimed_id": claimed_id,
            "link_id": link_id,
            "conflict": True,
        }
        return match

    if claimed_invoice:
        return {
            "invoice": claimed_invoice,
            "method": "exact",
            "score": 1.0,
            "runner_up": 0.0,
            "claimed_id": claimed_id,
            "link_id": link_id,
            "conflict": False,
        }

    if link_invoice:
        return {
            "invoice": link_invoice,
            "method": "link",
            "score": 1.0,
            "runner_up": 0.0,
            "claimed_id": claimed_id,
            "link_id": link_id,
            "conflict": False,
        }

    student_id = text(form.get("student_id"))
    claimed = to_float(form.get("amount_paid"))
    scored = []
    for invoice in invoice_list:
        if text(invoice.get("student_id")) != student_id:
            continue
        if not amount_matches(claimed, invoice):
            continue
        score = max(
            similarity(claimed_id, invoice.get("id")),
            similarity(link_id, invoice.get("id")),
        )
        scored.append((round(score, 3), invoice))

    if not scored:
        return empty_match("none", claimed_id, link_id)

    scored.sort(key=lambda item: (-item[0], text(item[1].get("id"))))
    best_score, best_invoice = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0

    if best_score < config.INVOICE_SIMILARITY_MIN:
        return empty_match("below_threshold", claimed_id, link_id, best_score, runner_up)

    if len(scored) > 1 and (best_score - runner_up) < config.INVOICE_MARGIN_MIN:
        return empty_match("ambiguous", claimed_id, link_id, best_score, runner_up)

    return {
        "invoice": best_invoice,
        "method": "fuzzy",
        "score": best_score,
        "runner_up": runner_up,
        "claimed_id": claimed_id,
        "link_id": link_id,
        "conflict": False,
    }
