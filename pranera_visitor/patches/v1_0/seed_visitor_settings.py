"""One-time seed of Visitor Settings from the values hardcoded in the Node
server (sqlapp) and the Ionic visitor-data page.

Not seeded on purpose:
  * Gate Users — the old app decided HO/JV by its own login names
    ('Security' → HO); those aren't Frappe users, so map them in Desk.
  * WhatsApp token / phone id — secrets don't belong in git. Enter them in
    Desk; enable_whatsapp stays off until you do.
"""
import frappe

from pranera_visitor.patches.v1_1.add_kongu_towns import KONGU_CITIES
ROTN_STATES = ["Tamil Nadu", "Kerala"]

REMARKS = [
	"Swatch Book Given", "Sample Ordered", "Sample Purchased", "Order Confirmed",
	"Unqualified", "Awaiting Customer Confirmation", "Swatch Given",
]
RECIPIENTS = [
	"ba@praneraservices.com", "textiles@praneraservices.com", "siva@praneraservices.com",
	"sivasm@praneraservices.com", "nandhakumar@praneraservices.com", "anne@praneraservices.com",
]


def _sp(name):
	return name if frappe.db.exists("Sales Person", name) else None


def execute():
	frappe.reload_doc("visitor_module", "doctype", "visitor_gate_user")
	frappe.reload_doc("visitor_module", "doctype", "visitor_department_rule")
	frappe.reload_doc("visitor_module", "doctype", "visitor_settings")

	s = frappe.get_single("Visitor Settings")
	if s.kongu_cities or s.department_rules:
		return  # already configured

	s.create_crm_lead = 1
	s.lead_temperature = "Hot"
	s.kongu_sales_person = _sp("Mahendran K")
	s.rotn_sales_person = _sp("Vijay Ram")
	s.roi_sales_person = _sp("Bhuvnesh Kumar")
	s.kongu_cities = "\n".join(KONGU_CITIES)
	s.rotn_states = "\n".join(ROTN_STATES)

	if _sp("Vinoth Kumar"):
		s.append("department_rules", {
			"department": "Garments", "assign_to": "Sales Person",
			"sales_person": "Vinoth Kumar", "whatsapp_notify": "7094958999",
		})
	if frappe.db.exists("User", "charlet@pss.com"):
		s.append("department_rules", {
			"department": "Others", "assign_to": "User",
			"lead_owner": "charlet@pss.com", "whatsapp_notify": "7094958999",
		})

	s.enable_whatsapp = 0
	s.whatsapp_api_version = "v22.0"
	s.whatsapp_template = "visitor_checkin_unassigned"

	s.enable_long_stay_alert = 1
	s.long_stay_minutes = 60
	s.long_stay_recipients = "\n".join(RECIPIENTS)

	s.remarks_options = "\n".join(REMARKS)

	s.flags.ignore_mandatory = True
	s.save(ignore_permissions=True)
