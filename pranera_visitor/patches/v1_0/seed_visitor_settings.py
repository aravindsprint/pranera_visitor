"""One-time seed of Visitor Settings from the values hardcoded in the Node
server (sqlapp) and the Ionic visitor-data page.

Not seeded on purpose:
  * Gate Users — the old app decided HO/JV by its own login names
    ('Security' → HO); those aren't Frappe users, so map them in Desk.
  * WhatsApp token / phone id — secrets don't belong in git. Enter them in
    Desk; enable_whatsapp stays off until you do.
"""
import frappe

KONGU_CITIES = ["Coimbatore", "Erode", "Tiruppur", "Salem", "Namakkal", "Karur"]
ROTN_STATES = ["Tamil Nadu", "Kerala"]

REMARKS = [
	"Swatch Book Given", "Sample Ordered", "Sample Purchased", "Order Confirmed",
	"Unqualified", "Awaiting Customer Confirmation", "Swatch Given",
]
COMMERCIAL_NAMES = [
	"2TF 240", "2TF ECO 220", "3TF 340", "3TF BRUSHED 280", "4 WAY", "4T PIQUE 250",
	"ADVANCE DOT KNIT 180", "ADVANCE KNIT 150", "ADVANCE KNIT 170", "AIRLITE 160",
	"AIRLITE 180", "AIRLITE 200", "AIRLITE 220 Z", "AIRTEX 110", "AIRTEX 200", "Others",
]
COLORS = [
	"BEIGE MELANGE", "BLACK MELANGE", "CAPRI BLUE MELANGE", "CARBON GREY MELANGE",
	"Customized Color",
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
	s.commercial_name_options = "\n".join(COMMERCIAL_NAMES)
	s.color_options = "\n".join(COLORS)

	s.flags.ignore_mandatory = True
	s.save(ignore_permissions=True)
