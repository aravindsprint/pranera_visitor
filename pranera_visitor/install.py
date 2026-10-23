"""Custom fields this app adds to Visitor Data (owned by Textiles And Garments).

Only what the app actually uses: follow-up remarks/notes, the linked
Customer and CRM Lead, and the app's own bookkeeping.

The old Node server also sent customer_type, customer_group, source,
commercial name, color and sample/bulk qty, but Visitor Data on
erp.pranera.in never had those fields (ERPNext dropped them), so no data
exists for them. v1.0 briefly added them as a "Customer Details" section;
OBSOLETE_FIELDS removes those Custom Fields again on migrate.

Everything is allow_on_submit so follow-up fields can still be edited after
the visitor has exited (exit submits the document).
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "Visitor Module"


def _f(fieldname, label, fieldtype, insert_after, **kw):
	return {
		"fieldname": fieldname,
		"label": label,
		"fieldtype": fieldtype,
		"insert_after": insert_after,
		"allow_on_submit": 1,
		"module": MODULE,
		**kw,
	}


def get_custom_fields():
	return {
		"Visitor Data": [
			_f("visitor_followup_section", "Follow-up", "Section Break", "territory", collapsible=1),
			_f("remarks", "Remarks", "Data", "visitor_followup_section"),
			_f("notes", "Notes", "Small Text", "remarks"),
			_f("visitor_followup_cb", None, "Column Break", "notes"),
			_f("customer", "Customer", "Link", "visitor_followup_cb", options="Customer", read_only=1),
			_f("crm_lead", "CRM Lead", "Link", "customer", options="CRM Lead", read_only=1),
			_f("visitor_app_section", "Visitor App", "Section Break", "crm_lead", collapsible=1),
			_f("checkin_source", "Check-in Source", "Data", "visitor_app_section", read_only=1),
			_f("checked_in_by", "Checked In By", "Link", "checkin_source", options="User", read_only=1),
			_f("checked_out_by", "Checked Out By", "Link", "checked_in_by", options="User", read_only=1),
			_f("visitor_app_cb", None, "Column Break", "checked_out_by"),
			_f("crm_lead_attempts", "CRM Lead Attempts", "Int", "visitor_app_cb", read_only=1, default="0"),
			_f("long_stay_notified", "Long Stay Notified", "Check", "crm_lead_attempts", read_only=1),
		]
	}


OBSOLETE_FIELDS = (
	"visitor_customer_section", "customer_type", "erpnext_customer_type", "customer_group",
	"source", "visitor_customer_cb", "commercial_name", "color", "sample_qty", "bulk_qty",
)


def remove_obsolete_fields():
	"""Drop the v1.0 "Customer Details" Custom Fields. Only rows this app
	created (module = Visitor Module) are touched. The DB columns stay —
	Frappe never drops columns on Custom Field delete — so nothing is lost."""
	for name in frappe.get_all(
		"Custom Field",
		{"dt": "Visitor Data", "module": MODULE, "fieldname": ["in", OBSOLETE_FIELDS]},
		pluck="name",
	):
		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)


def get_crm_lead_fields():
	# Company name typed at the gate. Organization (mandatory) stays empty
	# until sales confirms the real organization.
	return {
		"CRM Lead": [
			{
				"fieldname": "custom_temp_organization",
				"label": "Temp Organization",
				"fieldtype": "Data",
				"insert_after": "organization",
				"in_standard_filter": 1,
				"module": MODULE,
				"description": "Company name entered at the gate (Visitor App). Copy the confirmed name into Organization.",
			}
		]
	}


def apply_custom_fields():
	if frappe.db.exists("DocType", "CRM Lead"):
		create_custom_fields(get_crm_lead_fields(), update=True)
	if not frappe.db.exists("DocType", "Visitor Data"):
		# Textiles And Garments not installed on this site — nothing to extend.
		return
	remove_obsolete_fields()
	create_custom_fields(get_custom_fields(), update=True)
	show_mobile_as_text()
	frappe.clear_cache(doctype="Visitor Data")


def show_mobile_as_text():
	"""Visitor Data.mobile_no is a Phone field. Desk's Phone control renders
	'+91-XXXXXXXXXX' (the format both the Node app and this app store) as an
	empty box with a country picker. Show it as plain Data instead — same
	varchar column, stored values untouched. Property Setter, so the
	Textiles And Garments doctype JSON is not modified."""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	df = frappe.get_meta("Visitor Data").get_field("mobile_no")
	if df and df.fieldtype != "Data":
		make_property_setter(
			"Visitor Data", "mobile_no", "fieldtype", "Data", "Select",
			validate_fields_for_doctype=False,
		)
		frappe.clear_cache(doctype="Visitor Data")


def after_install():
	apply_custom_fields()


def after_migrate():
	apply_custom_fields()
