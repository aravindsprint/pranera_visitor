import frappe
from frappe.model.document import Document


def _lines(text):
	return [l.strip() for l in (text or "").replace(",", "\n").splitlines() if l.strip()]


class VisitorSettings(Document):
	def validate(self):
		seen = set()
		for row in self.gate_users:
			if row.user in seen:
				frappe.throw(f"Row {row.idx}: {row.user} is listed more than once in Gate Users")
			seen.add(row.user)
		for row in self.department_rules:
			if row.assign_to == "Sales Person" and not row.sales_person:
				frappe.throw(f"Department Rules row {row.idx}: Sales Person is required")
			if row.assign_to == "User" and not row.lead_owner:
				frappe.throw(f"Department Rules row {row.idx}: Lead Owner is required")


def get_settings():
	return frappe.get_cached_doc("Visitor Settings")


def option_list(fieldname):
	return [l.strip() for l in (get_settings().get(fieldname) or "").splitlines() if l.strip()]


def recipients():
	return _lines(get_settings().long_stay_recipients)
