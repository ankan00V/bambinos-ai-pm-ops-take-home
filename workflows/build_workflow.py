import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = Path(__file__).resolve().parent / "bambinos_renewal_engine.n8n.json"

RULES = r"""
const rows = (name) => $(name).all().map((item) => item.json);
const invoices = rows('Read invoices');
const forms = rows('Read forms');
const bookings = rows('Read bookings');
const schedule = rows('Read schedule');
const reference = rows('Read reference');

const text = (value) => (value === null || value === undefined ? '' : String(value).trim());
const num = (value) => {
  const parsed = parseFloat(text(value).replace(/[^0-9.\-]/g, ''));
  return Number.isNaN(parsed) ? 0 : parsed;
};
const truthy = (value) => ['yes', 'y', 'true', '1'].includes(text(value).toLowerCase());
const onlyDigits = (value) => text(value).toUpperCase().replace(/[^0-9X]/g, '');

const normalizePhone = (value) => {
  let digits = onlyDigits(value);
  if (digits.startsWith('00')) digits = digits.slice(2);
  if (digits.startsWith('971') && digits.length >= 12) return digits.slice(3);
  if (digits.startsWith('1') && digits.length === 11) return digits.slice(1);
  if (digits.startsWith('0') && digits.length > 10) digits = digits.slice(1);
  if (digits.startsWith('91') && digits.length === 12) digits = digits.slice(2);
  return digits;
};

const phoneScore = (left, right) => {
  const a = normalizePhone(left);
  const b = normalizePhone(right);
  if (!a || !b) return 0;
  if (a === b) return 1;
  const tail = Math.min(a.length, b.length, 6);
  return tail >= 4 && a.slice(-tail) === b.slice(-tail) ? 0.8 : 0;
};

const emailScore = (left, right) => {
  const a = text(left).toLowerCase();
  const b = text(right).toLowerCase();
  if (!a || !b) return 0;
  if (a === b) return 1;
  const partsA = a.split('@');
  const partsB = b.split('@');
  if (!partsA[1] || partsA[1] !== partsB[1]) return 0;
  return partsA[0].slice(0, 2) === partsB[0].slice(0, 2) ? 0.7 : 0;
};

const invoiceRef = (value) => {
  const runs = text(value).match(/\d+/g);
  return runs ? runs[runs.length - 1] : '';
};

const distance = (a, b) => {
  const matrix = [];
  for (let i = 0; i <= b.length; i += 1) {
    matrix.push(new Array(a.length + 1).fill(0));
    matrix[i][0] = i;
  }
  for (let j = 0; j <= a.length; j += 1) matrix[0][j] = j;
  for (let i = 1; i <= b.length; i += 1) {
    for (let j = 1; j <= a.length; j += 1) {
      const cost = b[i - 1] === a[j - 1] ? 0 : 1;
      matrix[i][j] = Math.min(matrix[i - 1][j] + 1, matrix[i][j - 1] + 1, matrix[i - 1][j - 1] + cost);
    }
  }
  return matrix[b.length][a.length];
};

const similarity = (a, b) => {
  const first = text(a).toLowerCase();
  const second = text(b).toLowerCase();
  if (!first || !second) return 0;
  return 1 - distance(first, second) / Math.max(first.length, second.length);
};

const parseDate = (value) => {
  const raw = text(value);
  if (!raw) return null;
  const parsed = new Date(raw.replace(' ', 'T'));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

let asOf = null;
[...invoices, ...forms, ...bookings, ...schedule].forEach((row) => {
  ['paid_at', 'created_at', 'updated_at', 'approved_at', 'allocated_at'].forEach((field) => {
    const parsed = parseDate(row[field]);
    if (parsed && (!asOf || parsed > asOf)) asOf = parsed;
  });
});

const hoursSince = (value) => {
  const parsed = parseDate(value);
  return parsed ? Math.max(0, (asOf - parsed) / 3600000) : 0;
};

const invoiceById = {};
invoices.forEach((row) => { invoiceById[text(row.id)] = row; });
const referenceByStudent = {};
reference.forEach((row) => { referenceByStudent[text(row.student_id)] = row; });
const batches = {};
reference.forEach((row) => {
  const key = text(row.current_classbatch_id);
  if (!batches[key]) batches[key] = row;
});
const bookingsByForm = {};
bookings.forEach((row) => {
  const key = text(row.faculty_form_id);
  if (!bookingsByForm[key]) bookingsByForm[key] = [];
  bookingsByForm[key].push(row);
});
const scheduleByBooking = {};
schedule.forEach((row) => {
  const key = text(row.bookingrequest_id);
  if (!scheduleByBooking[key]) scheduleByBooking[key] = [];
  scheduleByBooking[key].push(row);
});

const resolve = (form) => {
  const claimed = text(form.invoice_id);
  const link = text(form.invoice_link);
  const linkId = invoiceRef(link);
  if (invoiceById[claimed]) return { invoice: invoiceById[claimed], method: 'exact', score: 1 };
  if (invoiceById[linkId]) return { invoice: invoiceById[linkId], method: 'link', score: 1 };
  const claimedAmount = num(form.amount_paid);
  const scored = invoices
    .filter((invoice) => text(invoice.student_id) === text(form.student_id))
    .filter((invoice) => Math.abs(num(invoice.net_amount) - claimedAmount) <= Math.max(1, num(invoice.net_amount) * 0.005))
    .map((invoice) => ({ invoice, score: Math.max(similarity(claimed, invoice.id), similarity(linkId, invoice.id)) }))
    .sort((a, b) => b.score - a.score);
  if (!scored.length) return { invoice: null, method: 'none', score: 0 };
  if (scored[0].score < 0.72) return { invoice: null, method: 'below_threshold', score: scored[0].score };
  if (scored.length > 1 && scored[0].score - scored[1].score < 0.05) return { invoice: null, method: 'ambiguous', score: scored[0].score };
  return { invoice: scored[0].invoice, method: 'fuzzy', score: scored[0].score };
};

const money = (value) => 'Rs ' + Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });

const block = (row, code, reason, owner, severity, sla) => Object.assign(row, {
  decision: 'EXCEPTION',
  primary_code: code,
  reason,
  owner,
  severity,
  sla_hours: sla,
  blocking: 'Yes',
  fallback_message: reason,
});

const approve = (row, reason) => Object.assign(row, {
  decision: 'AUTO_APPROVE',
  primary_code: 'R00',
  reason,
  owner: 'system',
  severity: 'Info',
  sla_hours: 0,
  blocking: 'No',
  fallback_message: reason,
});

const seenInvoices = {};
const output = [];

forms
  .slice()
  .sort((a, b) => text(a.created_at).localeCompare(text(b.created_at)))
  .forEach((form) => {
    const match = resolve(form);
    const invoice = match.invoice;
    const base = {
      record_type: 'form',
      record_id: text(form.id),
      student_id: text(form.student_id),
      student_name: text(form.student_name),
      educator_name: text(form.educator_name),
      match_method: match.method,
      match_score: Number(match.score.toFixed(3)),
    };

    if (!invoice) {
      output.push(block(Object.assign({}, base, { case_key: 'FORM-' + text(form.id), classbatch_id: text(form.current_classbatch_id), hours_in_state: hoursSince(form.created_at), audience: 'teacher' }),
        'R02', 'Form ' + text(form.id) + ' points at invoice ' + text(form.invoice_id) + ' which does not exist and cannot be repaired safely.', 'teacher', 'High', 4));
      return;
    }

    const caseKey = text(invoice.id);
    const row = Object.assign({}, base, {
      case_key: caseKey,
      classbatch_id: text(form.current_classbatch_id),
      invoice_id: caseKey,
      student_id: text(invoice.student_id),
      amount_collected: num(invoice.net_amount),
      hours_in_state: Number(hoursSince(invoice.paid_at || form.created_at).toFixed(1)),
      audience: 'ops_agent',
    });

    if (seenInvoices[caseKey]) {
      output.push(block(row, 'R04', 'Form ' + text(form.id) + ' repeats invoice ' + caseKey + '. The first form is already in the queue.', 'teacher', 'Low', 24));
      output[output.length - 1].blocking = 'No';
      return;
    }
    seenInvoices[caseKey] = true;

    const referenceRow = referenceByStudent[text(invoice.student_id)] || null;
    const status = text(invoice.payment_status).toLowerCase();

    if (!['paid', 'partially_paid'].includes(status)) {
      return output.push(block(row, 'R07', 'Invoice ' + caseKey + ' is ' + text(invoice.payment_status) + ' with no settled amount, but a form was submitted as paid.', 'parent', 'High', 24));
    }

    const billed = num(invoice.amount);
    const collected = num(invoice.net_amount);
    const discount = num(invoice.discount_amount);
    const claimed = num(form.amount_paid);
    const tolerance = Math.max(1, billed * 0.005);
    const expected = billed - discount;

    if (text(invoice.payment_type).toLowerCase() !== 'full' || collected + tolerance < expected) {
      return output.push(block(row, 'R06', 'Invoice ' + caseKey + ' billed ' + money(billed) + ' and ' + money(collected) + ' arrived (' + text(invoice.payment_type) + '). The form claims ' + money(claimed) + '.', 'finance', 'High', 4));
    }

    if (Math.abs(claimed - collected) > 1) {
      return output.push(block(row, 'R05', 'Form claims ' + money(claimed) + ' but invoice ' + caseKey + ' collected ' + money(collected) + '.', 'finance', 'High', 4));
    }

    if (!referenceRow) {
      return output.push(block(row, 'R10', 'Student ' + text(invoice.student_id) + ' is not in the active batch reference.', 'ops_agent', 'High', 4));
    }

    const phone = phoneScore(invoice.mobile, referenceRow.registered_mobile_masked);
    const email = emailScore(invoice.email, referenceRow.registered_email_masked);
    if (text(form.student_id) !== text(invoice.student_id)) {
      return output.push(block(row, 'R11', 'Form is for student ' + text(form.student_id) + ' but the invoice belongs to ' + text(invoice.student_id) + '.', 'ops_agent', 'High', 4));
    }
    if (phone < 0.8 && email < 0.8) {
      return output.push(block(row, 'R12', 'Invoice was paid from ' + text(invoice.mobile) + ', which matches neither the registered mobile (' + text(referenceRow.registered_mobile_masked) + ') nor the registered email.', 'ops_agent', 'Medium', 4));
    }

    const batchId = text(form.current_classbatch_id);
    const batch = batches[batchId] || null;
    if (!truthy(form.continue_same_batch)) {
      return output.push(block(Object.assign(row, { audience: 'parent' }), 'R09', 'Batch change requested. Currently ' + text(referenceRow.batch_days) + ' at ' + text(referenceRow.batch_start_time) + ', form asks for ' + text(form.preferred_days) + ' at ' + text(form.preferred_time_slot) + '.', 'parent', 'Medium', 8));
    }
    if (!batch) {
      return output.push(block(row, 'R23', 'Batch ' + batchId + ' is not in the active batch reference.', 'ops_agent', 'High', 4));
    }
    if (text(referenceRow.current_classbatch_id) !== batchId) {
      return output.push(block(row, 'R15', 'Form names batch ' + batchId + ' but the student is on ' + text(referenceRow.current_classbatch_id) + '.', 'ops_agent', 'Medium', 4));
    }
    if (text(form.educator_id) !== text(referenceRow.educator_id)) {
      return output.push(block(row, 'R13', 'Form credits teacher ' + text(form.educator_id) + ' but the record has ' + text(referenceRow.educator_id) + '.', 'ops_agent', 'High', 4));
    }
    if (num(form.sessions_purchased) <= 0) {
      return output.push(block(row, 'R16', 'Form records zero sessions.', 'teacher', 'Medium', 8));
    }

    const rooms = bookingsByForm[text(form.id)] || [];
    const sessions = rooms.reduce((all, booking) => all.concat(scheduleByBooking[text(booking.id)] || []), []);
    if (text(form.approval_status).toLowerCase() === 'approved') {
      if (!rooms.length) {
        return output.push(block(row, 'R21', 'Form was approved but no booking request exists.', 'ops_agent', 'High', 4));
      }
      if (!sessions.length) {
        return output.push(block(row, 'R20', 'Approved ' + text(form.approved_at) + ' and booking ' + text(rooms[0].id) + ' is still ' + text(rooms[0].request_status) + '.', 'ops_agent', 'High', 4));
      }
      row.decision = 'ALREADY_PROCESSED';
      row.primary_code = 'R17';
      row.reason = 'Already has ' + sessions.length + ' session rows.';
      row.owner = 'system';
      row.severity = 'Info';
      row.blocking = 'No';
      row.sla_hours = 0;
      return output.push(row);
    }

    const seatsLeft = num(batch.max_batch_size) - num(batch.active_students_count);
    if (seatsLeft <= 0) {
      return output.push(block(row, 'R08', 'Batch ' + batchId + ' is at ' + num(batch.active_students_count) + ' of ' + num(batch.max_batch_size) + ' seats. ' + money(collected) + ' has waited ' + row.hours_in_state + ' hours.', 'ops_agent', 'High', 4));
    }

    approve(row, 'Payment ' + money(collected) + ' matches invoice ' + caseKey + ' and batch ' + batchId + ' has ' + seatsLeft + ' free seats.');
    output.push(row);
  });

invoices.forEach((invoice) => {
  const caseKey = text(invoice.id);
  if (seenInvoices[caseKey]) return;
  const status = text(invoice.payment_status).toLowerCase();
  if (!['paid', 'partially_paid'].includes(status)) return;
  const referenceRow = referenceByStudent[text(invoice.student_id)] || null;
  if (!referenceRow) return;
  const backup = bookingsByForm['__none__'] || [];
  if (backup.length) return;
  const row = {
    case_key: caseKey,
    record_type: 'invoice',
    record_id: caseKey,
    invoice_id: caseKey,
    student_id: text(invoice.student_id),
    student_name: text(referenceRow.student_name_masked),
    educator_name: text(referenceRow.educator_name),
    classbatch_id: text(referenceRow.current_classbatch_id),
    amount_collected: num(invoice.net_amount),
    hours_in_state: Number(hoursSince(invoice.paid_at).toFixed(1)),
    audience: 'teacher',
    match_method: 'invoice',
    match_score: 1,
  };
  const batch = batches[text(referenceRow.current_classbatch_id)] || null;
  const seatsLeft = batch ? num(batch.max_batch_size) - num(batch.active_students_count) : 0;
  if (!batch || seatsLeft <= 0) {
    return output.push(block(row, 'R08', 'Batch ' + text(referenceRow.current_classbatch_id) + ' has no free seat for a paid renewal that arrived without a form.', 'ops_agent', 'High', 4));
  }
  approve(row, 'No teacher form was needed. Payment ' + money(num(invoice.net_amount)) + ' and the student record carry every field required to schedule batch ' + text(referenceRow.current_classbatch_id) + '.');
  output.push(row);
});

return output.map((row) => ({ json: row }));
"""


def node(name, node_type, version, position, parameters, notes=""):
    return {
        "parameters": parameters,
        "id": name.lower().replace(" ", "-"),
        "name": name,
        "type": node_type,
        "typeVersion": version,
        "position": position,
        "notes": notes,
    }


def sheet_params(sheet_name):
    return {
        "documentId": {"__rl": True, "value": "PASTE_SPREADSHEET_ID", "mode": "id"},
        "sheetName": {"__rl": True, "value": sheet_name, "mode": "name"},
        "options": {},
    }


def build():
    nodes = [
        node("Every 15 minutes", "n8n-nodes-base.scheduleTrigger", 1.2, [0, 0], {
            "rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]}
        }, "Runs the reconciliation every 15 minutes."),
        node("Read invoices", "n8n-nodes-base.googleSheets", 4.5, [220, 0], sheet_params("invoices")),
        node("Read forms", "n8n-nodes-base.googleSheets", 4.5, [440, 0], sheet_params("faculty_form_unapproved")),
        node("Read bookings", "n8n-nodes-base.googleSheets", 4.5, [660, 0], sheet_params("booking_requests")),
        node("Read schedule", "n8n-nodes-base.googleSheets", 4.5, [880, 0], sheet_params("class_schedule_bookings")),
        node("Read reference", "n8n-nodes-base.googleSheets", 4.5, [1100, 0], sheet_params("reference_active_batches_and_students")),
        node("Reconcile", "n8n-nodes-base.code", 2, [1320, 0], {"mode": "runOnceForAllItems", "jsCode": RULES.strip()},
             "Deterministic rules mirror of engine/rules.py. No LLM calls here."),
        node("Route", "n8n-nodes-base.switch", 3, [1540, 0], {
            "rules": {"values": [
                {"conditions": {"options": {"caseSensitive": True, "version": 2}, "conditions": [
                    {"leftValue": "={{ $json.decision }}", "rightValue": "AUTO_APPROVE", "operator": {"type": "string", "operation": "equals"}}
                ]}, "renameOutput": True, "outputKey": "auto"},
                {"conditions": {"options": {"caseSensitive": True, "version": 2}, "conditions": [
                    {"leftValue": "={{ $json.decision }}", "rightValue": "EXCEPTION", "operator": {"type": "string", "operation": "equals"}}
                ]}, "renameOutput": True, "outputKey": "exception"},
            ]},
            "options": {"fallbackOutput": "extra"},
        }),
        node("Append auto approved", "n8n-nodes-base.googleSheets", 4.5, [1760, -220], {
            "operation": "append",
            "documentId": {"__rl": True, "value": "PASTE_SPREADSHEET_ID", "mode": "id"},
            "sheetName": {"__rl": True, "value": "auto_approved", "mode": "name"},
            "columns": {"mappingMode": "autoMapInputData", "value": {}},
            "options": {},
        }),
        node("Create booking", "n8n-nodes-base.httpRequest", 4.2, [1980, -220], {
            "method": "POST",
            "url": "https://api.bambinos.live/internal/renewals/bookings",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ invoice_id: $json.invoice_id, student_id: $json.student_id, classbatch_id: $json.classbatch_id, sessions: 24, source: 'renewal_engine' }) }}",
            "options": {},
        }, "Writes the booking. Keep this node disabled until shadow mode ends."),
        node("Append exceptions", "n8n-nodes-base.googleSheets", 4.5, [1760, 220], {
            "operation": "append",
            "documentId": {"__rl": True, "value": "PASTE_SPREADSHEET_ID", "mode": "id"},
            "sheetName": {"__rl": True, "value": "exceptions", "mode": "name"},
            "columns": {"mappingMode": "autoMapInputData", "value": {}},
            "options": {},
        }),
        node("Draft with LLM", "n8n-nodes-base.httpRequest", 4.2, [1980, 220], {
            "method": "POST",
            "url": "https://api.openai.com/v1/chat/completions",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ model: 'gpt-4.1-mini', temperature: 0.2, messages: [ { role: 'system', content: $('Reconcile').first().json.system_prompt }, { role: 'user', content: JSON.stringify($json) } ] }) }}",
            "options": {},
        }, "Optional. If this node errors, the next node keeps the template draft."),
        node("Normalise draft", "n8n-nodes-base.code", 2, [2200, 220], {"mode": "runOnceForEachItem", "jsCode": (
            "const item = $json;\n"
            "const draft = item.choices && item.choices[0] && item.choices[0].message && item.choices[0].message.content;\n"
            "return { json: { message: (draft || item.fallback_message || item.reason || '').trim() } };\n"
        ).strip()}, "Falls back to the deterministic template when the LLM node fails."),
        node("Send Slack", "n8n-nodes-base.slack", 2.3, [2420, 220], {
            "select": "channel",
            "channelId": {"__rl": True, "value": "renewals-exceptions", "mode": "name"},
            "text": "={{ $json.message }}",
            "otherOptions": {},
        }),
        node("Is WhatsApp", "n8n-nodes-base.if", 2.2, [2640, 220], {
            "conditions": {"options": {"caseSensitive": True, "version": 2}, "conditions": [
                {"leftValue": "={{ $('Normalise draft').item.json.channel }}", "rightValue": "WhatsApp", "operator": {"type": "string", "operation": "equals"}}
            ]},
        }),
        node("Send WhatsApp", "n8n-nodes-base.httpRequest", 4.2, [2860, 120], {
            "method": "POST",
            "url": "https://graph.facebook.com/v20.0/PASTE_PHONE_NUMBER_ID/messages",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ messaging_product: 'whatsapp', to: $('Normalise draft').item.json.recipient, type: 'text', text: { body: $json.message } }) }}",
            "options": {},
        }),
    ]

    connections = {
        "Every 15 minutes": {"main": [[{"node": "Read invoices", "type": "main", "index": 0}]]},
        "Read invoices": {"main": [[{"node": "Read forms", "type": "main", "index": 0}]]},
        "Read forms": {"main": [[{"node": "Read bookings", "type": "main", "index": 0}]]},
        "Read bookings": {"main": [[{"node": "Read schedule", "type": "main", "index": 0}]]},
        "Read schedule": {"main": [[{"node": "Read reference", "type": "main", "index": 0}]]},
        "Read reference": {"main": [[{"node": "Reconcile", "type": "main", "index": 0}]]},
        "Reconcile": {"main": [[{"node": "Route", "type": "main", "index": 0}]]},
        "Route": {"main": [
            [{"node": "Append auto approved", "type": "main", "index": 0}],
            [{"node": "Append exceptions", "type": "main", "index": 0}],
        ]},
        "Append auto approved": {"main": [[{"node": "Create booking", "type": "main", "index": 0}]]},
        "Append exceptions": {"main": [[{"node": "Draft with LLM", "type": "main", "index": 0}]]},
        "Draft with LLM": {"main": [[{"node": "Normalise draft", "type": "main", "index": 0}]]},
        "Normalise draft": {"main": [[{"node": "Send Slack", "type": "main", "index": 0}]]},
        "Send Slack": {"main": [[{"node": "Is WhatsApp", "type": "main", "index": 0}]]},
        "Is WhatsApp": {"main": [
            [{"node": "Send WhatsApp", "type": "main", "index": 0}],
            [],
        ]},
    }

    return {
        "name": "Bambinos renewal reconciliation",
        "nodes": nodes,
        "connections": connections,
        "active": False,
        "settings": {"executionOrder": "v1", "saveManualExecutions": True},
        "versionId": "bambinos-renewal-1",
        "meta": {"templateCredsSetupCompleted": False},
        "tags": [],
    }


def main():
    workflow = build()
    TARGET.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote {}".format(TARGET))
    print("nodes {}".format(len(workflow["nodes"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
