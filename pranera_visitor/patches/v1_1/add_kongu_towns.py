"""Add the KONGU-region towns the old city list missed (Avinashi, Kotagiri,
Palladam, …) to Visitor Settings → KONGU Cities. Existing entries and any
the admin added by hand are kept; only missing names are appended."""
import frappe

# Old Ionic list (first 6) + Kovai + Tiruppur / Coimbatore / Erode / Nilgiris
# district towns seen at the gate on erp.pranera.in.
KONGU_CITIES = [
	"Coimbatore", "Kovai", "Erode", "Tiruppur", "Salem", "Namakkal", "Karur",
	"Avinashi", "Palladam", "Udumalpet", "Kangeyam", "Dharapuram", "Pollachi",
	"Mettupalayam", "Nilgiris", "Ooty", "Kotagiri", "Gobichettipalayam", "Perundurai", "Bhavani",
]


def execute():
	frappe.reload_doc("visitor_module", "doctype", "visitor_settings")
	s = frappe.get_single("Visitor Settings")
	current = [c.strip() for c in (s.kongu_cities or "").splitlines() if c.strip()]
	have = {c.lower() for c in current}
	merged = current + [c for c in KONGU_CITIES if c.lower() not in have]
	if merged != current:
		frappe.db.set_single_value("Visitor Settings", "kongu_cities", "\n".join(merged))
