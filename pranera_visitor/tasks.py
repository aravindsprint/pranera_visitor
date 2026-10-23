"""Scheduler jobs (every 5 minutes, see hooks.py)."""
import frappe
from frappe.utils import add_to_date, cint, now_datetime

from pranera_visitor.crm import LEAD_DEPARTMENTS, MAX_LEAD_ATTEMPTS, enqueue_lead
from pranera_visitor.utils import duration_since, today_start
from pranera_visitor.visitor_module.doctype.visitor_settings.visitor_settings import (
	get_settings,
	recipients,
)


def send_long_stay_alerts():
	"""Port of the Ionic page's 1-minute timer + /api/sendVistorDataViaEmail.
	The old version ran in every open browser tab, so it could fire several
	times or not at all; this runs once on the server and marks each visit
	long_stay_notified so nobody gets the same visitor twice."""
	s = get_settings()
	if not cint(s.enable_long_stay_alert):
		return
	to = recipients()
	if not to:
		return
	minutes = cint(s.long_stay_minutes) or 60
	cutoff = add_to_date(now_datetime(), minutes=-minutes)

	rows = frappe.get_all(
		"Visitor Data",
		{
			"docstatus": 0,
			"out": ["!=", "Yes"],
			"date": ["between", [today_start(), cutoff]],
			"long_stay_notified": 0,
		},
		["name", "name1", "company_name", "mobile_no", "location", "date"],
		order_by="date asc",
	)
	if not rows:
		return

	body_rows = "".join(
		f"<tr><td>{frappe.utils.escape_html(r.name1 or '')}</td>"
		f"<td>{frappe.utils.escape_html(r.company_name or '')}</td>"
		f"<td>{duration_since(r.date)}</td><td>{r.mobile_no or ''}</td>"
		f"<td>{r.location or ''}</td><td>{frappe.utils.format_datetime(r.date, 'dd-MM-yyyy hh:mm a')}</td></tr>"
		for r in rows
	)
	message = (
		f"<h3>The following visitors have been inside for more than {minutes} minutes:</h3>"
		"<table border='1' cellpadding='5' cellspacing='0'>"
		"<thead><tr><th>Name</th><th>Company</th><th>Duration</th><th>Mobile</th>"
		"<th>Location</th><th>Check-In Time</th></tr></thead>"
		f"<tbody>{body_rows}</tbody></table><p>Please follow up with these visitors.</p>"
	)
	frappe.sendmail(
		recipients=to,
		subject="Alert: Long Visitor Duration",
		message=message,
		now=True,
	)
	for r in rows:
		frappe.db.set_value("Visitor Data", r.name, "long_stay_notified", 1, update_modified=False)
	frappe.db.commit()


def retry_missing_crm_leads():
	"""Port of syncMissingCrmLeads: today's app check-ins that still have no
	lead (job failed / worker was down) get re-queued, up to 3 attempts."""
	s = get_settings()
	if not cint(s.create_crm_lead):
		return
	names = frappe.get_all(
		"Visitor Data",
		{
			"checkin_source": "Visitor App",
			"department": ["in", list(LEAD_DEPARTMENTS)],
			"date": [">=", today_start()],
			"creation": ["<", add_to_date(now_datetime(), minutes=-3)],
			"crm_lead": ["is", "not set"],
			"crm_lead_attempts": ["<", MAX_LEAD_ATTEMPTS],
			"docstatus": ["!=", 2],
		},
		pluck="name",
	)
	for name in names:
		enqueue_lead(name)
