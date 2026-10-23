import re

import frappe
from frappe.utils import get_datetime, now_datetime, nowdate


def normalize_mobile(raw):
	"""Bare 10-digit number from '+91-98…', '919…', '09…' etc. (port of normalizeMobile)."""
	digits = re.sub(r"\D", "", str(raw or ""))
	if len(digits) == 12 and digits.startswith("91"):
		return digits[2:]
	if len(digits) == 11 and digits.startswith("0"):
		return digits[1:]
	return digits[-10:]


def display_mobile(raw):
	"""Canonical storage format — same as the Ionic app sent for new visitors."""
	ten = normalize_mobile(raw)
	return f"+91-{ten}" if ten else ""


def clean_str(val):
	"""Port of safeStr(): never store '[object Object]' / empty strings."""
	if val is None:
		return None
	if isinstance(val, dict):
		val = val.get("label") or val.get("value") or ""
	s = str(val).strip()
	return None if s in ("", "[object Object]") else s


def duration_since(start, end=None):
	"""'HH:MM:SS' between two datetimes (hours may exceed 24, like the old app)."""
	secs = max(0, int((get_datetime(end or now_datetime()) - get_datetime(start)).total_seconds()))
	return f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"


def today_start():
	return f"{nowdate()} 00:00:00"


def link_value_or_none(doctype, fieldname, value):
	"""Return value only if it's a valid target for that Link field, else None.

	Used for CRM Lead territory/source and Visitor Data territory: the old
	code always sent 'ROI', which isn't a Territory on erp.pranera.in, so
	those inserts failed link validation.
	"""
	if not value:
		return None
	df = frappe.get_meta(doctype).get_field(fieldname)
	if not df:
		return None
	if df.fieldtype != "Link":
		return value
	return value if frappe.db.exists(df.options, value) else None
