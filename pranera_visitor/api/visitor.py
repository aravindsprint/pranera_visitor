"""Visitor App API — replaces the visitor half of the Node server (sqlapp).

Node endpoint                          → here
/api/getVistorDataFromERPNext          → lookup_mobile
/api/getVisitorByMobile (SQLite)       → lookup_mobile (state/city come from the same rows)
/api/postVistorDataToDB                → check_in
/api/getVisitorReportFromDBAllDataForOut → get_active_visitors
/api/setVisitorReportExit (+ postVisitorData) → mark_exit
/api/updateVisitorSalesPerson          → update_visitor
/api/getCustomerByMobile               → lookup_customer
/api/createCustomerFromVisitor         → create_customer
/api/getVisitorReportFromDBAllData     → get_visitor_report
/api/getSalesPersonList                → get_boot (sales_persons)
/api/getSecurityScanReport (port 3000) → get_security_scan_report
/api/sendVistorDataViaEmail            → tasks.send_long_stay_alerts (scheduler)

Visitor Data is the single source of truth — no SQLite, no sync crons.
"""
import json

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, getdate, now_datetime

from pranera_visitor import crm
from pranera_visitor.utils import (
	clean_str,
	display_mobile,
	duration_since,
	link_value_or_none,
	normalize_mobile,
	today_start,
)
from pranera_visitor.visitor_module.doctype.visitor_settings.visitor_settings import (
	get_settings,
	option_list,
)

DT = "Visitor Data"
LOCATIONS = ("HO", "JV")
DEPARTMENTS = ("Fabric", "Garments", "Others")

LIST_FIELDS = [
	"name", "date", "name1", "company_name", "mobile_no", "location", "department",
	"state", "city", "territory", "out", "out_date", "duration", "docstatus",
	"sales_person", "remarks", "notes",
	"customer", "crm_lead", "checked_in_by", "long_stay_notified",
]

EDITABLE_FIELDS = ("sales_person", "territory", "remarks", "notes", "state", "city")


# ── Access ───────────────────────────────────────────────────────────────────
def _require_gate():
	if frappe.session.user == "Guest":
		raise frappe.PermissionError(_("Please log in"))
	roles = set(frappe.get_roles())
	if not roles & {"Visitor Gate", "System Manager"}:
		raise frappe.PermissionError(_("You need the Visitor Gate role to use the Visitor App"))


def _gate():
	"""(location, can_view_all) for the current user, from Visitor Settings.
	System Managers who aren't mapped can see every gate."""
	user = frappe.session.user
	for row in get_settings().gate_users:
		if row.user == user:
			return row.location, bool(cint(row.can_view_all_locations))
	if "System Manager" in frappe.get_roles():
		return None, True
	return None, False


def _resolve_location(requested=None, for_write=False):
	loc, view_all = _gate()
	if view_all and requested in LOCATIONS:
		return requested
	if loc:
		return loc
	if view_all:
		if for_write:
			frappe.throw(_("Pick a gate (HO / JV) before checking a visitor in"))
		return None  # read: all locations
	frappe.throw(_("Your user isn't mapped to a gate. Ask an admin to add you in Visitor Settings → Gate Users."))


def _row(d):
	d = frappe._dict(d)
	d.visitor_name = d.name1
	d.mobile_10 = normalize_mobile(d.mobile_no)
	if not d.out_date and d.date and d.docstatus == 0:
		d.live_duration = duration_since(d.date)
	return d


def _parse(data):
	if isinstance(data, str):
		data = json.loads(data or "{}")
	return frappe._dict(data or {})


# ── Boot / CSRF ──────────────────────────────────────────────────────────────
@frappe.whitelist()
def get_csrf_token():
	"""Lets the offline-cached SPA shell (which has no Jinja-injected token)
	fetch one before replaying queued check-ins."""
	if frappe.session.user == "Guest":
		return ""
	return frappe.sessions.get_csrf_token()


@frappe.whitelist()
def get_boot():
	_require_gate()
	loc, view_all = _gate()
	return {
		"user": frappe.session.user,
		"full_name": frappe.utils.get_fullname(frappe.session.user),
		"location": loc,
		"can_view_all": view_all,
		"is_mapped": bool(loc) or view_all,
		"locations": list(LOCATIONS),
		"departments": list(DEPARTMENTS),
		"options": {
			"remarks": option_list("remarks_options"),
			# Only used when creating a Customer from the Edit sheet.
			"erpnext_customer_types": ["Company", "Individual", "Partnership"],
		},
		"customer_groups": frappe.get_all("Customer Group", {"is_group": 0}, pluck="name", order_by="name asc"),
		"sales_persons": frappe.get_all(
			"Sales Person", {"enabled": 1, "is_group": 0}, pluck="name", order_by="name asc"
		),
		"territories": frappe.get_all("Territory", {"is_group": 0}, pluck="name", order_by="name asc"),
		"long_stay_minutes": cint(get_settings().long_stay_minutes) or 60,
	}


# ── Check-in flow ────────────────────────────────────────────────────────────
def _active_today(ten, location=None):
	filters = {
		"mobile_no": ["like", f"%{ten}"],
		"docstatus": 0,
		"date": [">=", today_start()],
		"out": ["!=", "Yes"],
	}
	if location:
		filters["location"] = location
	return frappe.get_all(DT, filters, LIST_FIELDS, order_by="date desc", limit=1)


@frappe.whitelist()
def lookup_mobile(mobile_no, location=None):
	"""Step 1 of check-in. Returns one of:
	  inside          — already checked in today and not exited
	  returning_today — visited earlier today (exited) → re-check-in with same details
	  known           — visited on an earlier day → prefill the form
	  new             — never seen → blank form
	"""
	_require_gate()
	ten = normalize_mobile(mobile_no)
	if len(ten) != 10:
		frappe.throw(_("Enter a valid 10-digit mobile number"))

	active = _active_today(ten)
	if active:
		return {"status": "inside", "visitor": _row(active[0])}

	rows = frappe.get_all(
		DT, {"mobile_no": ["like", f"%{ten}"], "docstatus": ["!=", 2]},
		LIST_FIELDS + ["creation"], order_by="creation desc", limit=10,
	)
	if not rows:
		return {"status": "new", "last": None}

	last = _row(rows[0])
	# State/city weren't always stored (old [object Object] bug, SQLite-only
	# rows) — take them from the most recent row that has them.
	if not clean_str(last.state) or not clean_str(last.city):
		for r in rows:
			if clean_str(r.state) and clean_str(r.city):
				last.state, last.city = r.state, r.city
				break
	last.state, last.city = clean_str(last.state), clean_str(last.city)

	visited_today = str(get_datetime(rows[0].creation).date()) == str(getdate())
	return {"status": "returning_today" if visited_today else "known", "last": last}


def _checkin_time(client_time):
	"""Offline check-ins replay later — keep the time the guard actually
	recorded, as long as it's plausible (last 24h, not in the future)."""
	now = now_datetime()
	if not client_time:
		return now
	try:
		t = get_datetime(client_time)
	except Exception:
		return now
	if t > add_to_date(now, minutes=5) or t < add_to_date(now, hours=-24):
		return now
	return min(t, now)


def _unique_idx():
	"""Visitor Data has custom `idx` and `id` columns (Data, UNIQUE) added for
	the old Node sync, which shadow Frappe's own idx. Frappe would insert
	idx = 0 → "idx must be unique" on the second row. The Node app sent
	unix-seconds + SQLite rowid; microseconds since epoch is unique enough
	here and stays numeric like the existing values."""
	import time

	for _attempt in range(5):
		candidate = str(time.time_ns() // 1000)
		if not frappe.db.exists(DT, {"idx": candidate}):
			return candidate
		time.sleep(0.001)
	return f"{time.time_ns() // 1000}{frappe.generate_hash(length=4)}"


@frappe.whitelist(methods=["POST"])
def check_in(data, client_id=None):
	"""Create a Visitor Data row (draft = inside). Idempotent on client_id, so
	the offline queue can safely retry. Fires the CRM Lead job after commit."""
	_require_gate()
	d = _parse(data)

	if client_id:
		existing = frappe.db.get_value(DT, {"id": client_id}, LIST_FIELDS, as_dict=True)
		if existing:
			return {"status": "duplicate", "visitor": _row(existing)}

	ten = normalize_mobile(d.mobile_no)
	name = clean_str(d.name)
	company = clean_str(d.company_name)
	city = clean_str(d.city)
	state = clean_str(d.state)
	department = clean_str(d.department)
	if len(ten) != 10:
		frappe.throw(_("Enter a valid 10-digit mobile number"))
	if not name or len(name) < 3:
		frappe.throw(_("Name should be at least 3 characters"))
	if not company or len(company) < 3:
		frappe.throw(_("Company Name should be at least 3 characters"))
	if department not in DEPARTMENTS:
		frappe.throw(_("Pick a department"))
	if not city:
		# Same backstop the Node server added — city must never be blank.
		frappe.throw(_("City is required"))

	location = _resolve_location(d.location, for_write=True)

	active = _active_today(ten)
	if active:
		return {"status": "inside", "visitor": _row(active[0])}

	zone = crm.territory_zone(state, city)
	doc = frappe.get_doc({
		"doctype": DT,
		"date": _checkin_time(d.checked_in_at),
		"name1": name,
		"company_name": company,
		"mobile_no": display_mobile(ten),
		"location": location,
		"department": department,
		"state": state,
		"city": city,
		# "" (not None) on purpose: None lets Frappe fill the user/global
		# default ("All Territories"), which looked like a real value.
		"territory": link_value_or_none(DT, "territory", zone) or "",
		"sales_person": "",
		"id": client_id or f"{ten}-{now_datetime().strftime('%Y%m%d%H%M%S')}",
		"idx": _unique_idx(),
		"checkin_source": "Visitor App",
		"checked_in_by": frappe.session.user,
	})
	doc.insert(ignore_permissions=True)
	crm.enqueue_lead(doc.name)
	return {"status": "checked_in", "visitor": _row(doc.as_dict())}


@frappe.whitelist()
def get_active_visitors(location=None):
	_require_gate()
	loc = _resolve_location(location)
	filters = {"docstatus": 0, "date": [">=", today_start()], "out": ["!=", "Yes"]}
	if loc:
		filters["location"] = loc
	return [_row(r) for r in frappe.get_all(DT, filters, LIST_FIELDS, order_by="date desc", limit=500)]


@frappe.whitelist(methods=["POST"])
def mark_exit(name):
	"""Exit = out Yes + out_date + duration, then submit (same as the Node
	PUT with docstatus 1). Calling it twice is harmless."""
	_require_gate()
	doc = frappe.get_doc(DT, name)
	_check_location(doc)
	if doc.docstatus == 1:
		return {"status": "already_exited", "visitor": _row(doc.as_dict())}
	if doc.docstatus == 2:
		frappe.throw(_("This visit was cancelled"))
	now = now_datetime()
	doc.out = "Yes"
	doc.out_date = now
	doc.duration = duration_since(doc.date, now)
	doc.checked_out_by = frappe.session.user
	doc.flags.ignore_permissions = True
	doc.submit()
	return {"status": "exited", "visitor": _row(doc.as_dict())}


def _check_location(doc):
	loc, view_all = _gate()
	if not view_all and loc and doc.location != loc:
		frappe.throw(_("{0} was checked in at {1}, not your gate ({2})").format(doc.name, doc.location, loc))


# ── Edit visitor (follow-up details) ────────────────────────────────────────
@frappe.whitelist(methods=["POST"])
def update_visitor(name, data, link_contact_to_customer=0):
	"""Port of updateVisitorSalesPerson. Fields are allow_on_submit, so this
	works whether the visitor is still inside or has exited.

	link_contact_to_customer: the old app's "matched by company name" branch —
	the Customer exists but has no Contact for this mobile, so add one."""
	_require_gate()
	d = _parse(data)
	doc = frappe.get_doc(DT, name)
	_check_location(doc)
	for f in EDITABLE_FIELDS:
		if f in d:
			val = d.get(f)
			val = clean_str(val)
			if f in ("sales_person", "customer_group", "territory"):
				val = link_value_or_none(DT, f, val)
			doc.set(f, val)
	doc.flags.ignore_permissions = True
	doc.save()

	result = {"visitor": _row(doc.as_dict())}
	if cint(link_contact_to_customer):
		found = crm.find_customer(doc.mobile_no, doc.company_name)
		if found.get("status") == "found" and found.get("matched_by") == "company_name":
			ten = normalize_mobile(doc.mobile_no)
			crm.create_contact(doc.name1, ten, found["customer_id"])
			frappe.db.set_value(DT, doc.name, "customer", found["customer_id"], update_modified=False)
			result["contact_linked_to"] = found["customer_name"]
	return result


@frappe.whitelist()
def lookup_customer(name):
	_require_gate()
	doc = frappe.get_doc(DT, name)
	return crm.find_customer(doc.mobile_no, doc.company_name)


@frappe.whitelist(methods=["POST"])
def create_customer(name, data=None):
	_require_gate()
	doc = frappe.get_doc(DT, name)
	_check_location(doc)
	res = crm.create_customer_for_visitor(doc, _parse(data))
	frappe.db.set_value(DT, doc.name, "customer", res["customer_id"], update_modified=False)
	return res


# ── Reports ──────────────────────────────────────────────────────────────────
def _date_range(from_date, to_date, max_days=93):
	f = getdate(from_date) if from_date else getdate()
	t = getdate(to_date) if to_date else f
	if t < f:
		f, t = t, f
	if (t - f).days > max_days:
		frappe.throw(_("Pick a range of {0} days or less").format(max_days))
	return f, t


@frappe.whitelist()
def get_visitor_report(from_date=None, to_date=None, location=None):
	_require_gate()
	f, t = _date_range(from_date, to_date)
	loc = _resolve_location(location)
	filters = {"date": ["between", [f"{f} 00:00:00", f"{t} 23:59:59"]], "docstatus": ["!=", 2]}
	if loc:
		filters["location"] = loc
	rows = [_row(r) for r in frappe.get_all(DT, filters, LIST_FIELDS, order_by="date desc", limit=5000)]
	return {
		"rows": rows,
		"summary": {
			"total": len(rows),
			"inside": sum(1 for r in rows if r.docstatus == 0 and r.out != "Yes"),
			"unique_visitors": len({r.mobile_10 for r in rows}),
			"leads": sum(1 for r in rows if r.crm_lead),
		},
	}


@frappe.whitelist()
def get_security_scan_report(from_date=None, to_date=None, scanned_from=None):
	"""Sales Invoices and Stock Entries posted in the range with their gate
	scan status (security_passed / security_scanned_date / security_scanned_from
	custom fields). Rebuilt here because the old page called a separate
	server on port 3000."""
	_require_gate()
	f, t = _date_range(from_date, to_date)
	scan_fields = ("security_passed", "security_scanned_date", "security_scanned_from")
	missing = []

	def fetch(doctype, extra):
		# The security_* custom fields exist on erp.pranera.in but not on every
		# site (e.g. a local dev copy). Select only what exists so the report
		# degrades to "no scan data" instead of a SQL error.
		meta = frappe.get_meta(doctype)
		have = [fn for fn in scan_fields if meta.has_field(fn)]
		missing.extend(f"{doctype}.{fn}" for fn in scan_fields if fn not in have)
		filters = {"docstatus": 1, "posting_date": ["between", [f, t]]}
		if scanned_from:
			if "security_scanned_from" not in have:
				return []
			filters["security_scanned_from"] = scanned_from
		rows = frappe.get_all(
			doctype, filters, ["name", "posting_date", *have, *extra],
			order_by="posting_date desc, name desc", limit=5000,
		)
		for r in rows:
			for fn in scan_fields:
				r.setdefault(fn, None)
		return rows

	invoices = fetch("Sales Invoice", ["customer_name as party", "grand_total"])
	stock = fetch("Stock Entry", ["stock_entry_type as party", "total_outgoing_value as grand_total"])

	def summary(rows):
		passed = sum(1 for r in rows if r.security_passed == "Yes")
		return {"total": len(rows), "passed": passed, "pending": len(rows) - passed}

	scanned_from_options = (
		frappe.get_meta("Sales Invoice").get_field("security_scanned_from").options or ""
	).split("\n") if frappe.get_meta("Sales Invoice").get_field("security_scanned_from") else []

	return {
		"sales_invoices": invoices,
		"stock_entries": stock,
		"summary": {"sales_invoices": summary(invoices), "stock_entries": summary(stock)},
		"scanned_from_options": [o for o in scanned_from_options if o],
		"missing_fields": missing,
	}
