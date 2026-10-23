"""Custom fields this app adds to Visitor Data (owned by Textiles And Garments).

The old Node server sent customer_type, customer_group, source, commercial
name, color, sample/bulk qty, remarks and notes to ERPNext, but Visitor Data
never had those fields, so ERPNext silently dropped them. They are added here.

Everything is allow_on_submit so the follow-up fields can still be edited
after the visitor has exited (exit submits the document).
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
			_f("visitor_customer_section", "Customer Details", "Section Break", "territory", collapsible=1),
			_f("customer_type", "Customer Type", "Select", "visitor_customer_section", options="\nExisting\nNew"),
			_f("erpnext_customer_type", "ERPNext Customer Type", "Select", "customer_type",
			   options="\nCompany\nIndividual\nPartnership"),
			_f("customer_group", "Customer Group", "Link", "erpnext_customer_type", options="Customer Group"),
			_f("source", "Source", "Select", "customer_group",
			   options="\nWalk-In\nInbound Call\nExpo\nOutbound Call"),
			_f("visitor_customer_cb", None, "Column Break", "source"),
			_f("commercial_name", "Commercial Name", "Data", "visitor_customer_cb"),
			_f("color", "Color", "Data", "commercial_name"),
			_f("sample_qty", "Sample Qty", "Float", "color"),
			_f("bulk_qty", "Bulk Qty", "Float", "sample_qty"),
			_f("visitor_followup_section", "Follow-up", "Section Break", "bulk_qty", collapsible=1),
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


def apply_custom_fields():
	if not frappe.db.exists("DocType", "Visitor Data"):
		# Textiles And Garments not installed on this site — nothing to extend.
		return
	create_custom_fields(get_custom_fields(), update=True)
	show_mobile_as_text()


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
