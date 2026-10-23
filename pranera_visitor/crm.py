"""CRM Lead / Contact / Customer logic — port of triggerCrmLeadCreation,
getCustomerByMobile and createCustomerFromVisitor from the Node server.

Runs inside Frappe now, so it uses the DB directly instead of REST calls
with a hardcoded API token.
"""
import frappe
import requests
from frappe.utils import cint

from pranera_visitor.utils import link_value_or_none, normalize_mobile
from pranera_visitor.visitor_module.doctype.visitor_settings.visitor_settings import get_settings

MAX_LEAD_ATTEMPTS = 3

# Only these check-ins become CRM Leads. "Others" (couriers, vendors,
# interviews, service visits…) stay as Visitor Data only.
LEAD_DEPARTMENTS = ("Fabric", "Garments")


def wants_lead(department):
	return (department or "").strip().lower() in {d.lower() for d in LEAD_DEPARTMENTS}


# ── Territory ────────────────────────────────────────────────────────────────
def place_key(text):
	"""Spelling-tolerant key for state / city names typed at the gate.

	Production has rows like 'Tamilnadu' / 'Thirupur' next to 'Tamil Nadu' /
	'Tiruppur'; exact matching sent those visitors to ROI. Letters only,
	lower-case, no 'h', doubled letters collapsed:
	  Tiruppur, Tirupur, Thirupur → 'tirupur'
	  Tamil Nadu, Tamilnadu, TAMIL NADU → 'tamilnadu'"""
	s = "".join(ch for ch in (text or "").lower() if ch.isalpha()).replace("h", "")
	out = []
	for ch in s:
		if not out or out[-1] != ch:
			out.append(ch)
	return "".join(out)


TN = place_key("Tamil Nadu")
KL = place_key("Kerala")
# Every other state/UT — used only to tell "clearly not Tamil Nadu" apart
# from a misspelt or blank state.
OTHER_STATES = {place_key(x) for x in (
	"Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat",
	"Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
	"Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan",
	"Sikkim", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi",
	"Puducherry", "Jammu and Kashmir", "Ladakh", "Chandigarh", "Andaman and Nicobar Islands",
	"Lakshadweep", "Dadra and Nagar Haveli and Daman and Diu",
)}


def fuzzy_in(key, candidates, ratio=0.8):
	"""True if `key` is one of `candidates` allowing gate-typing slips:
	exact, a 4+ letter prefix ('coim' → coimbatore, 'karu' → karur), or
	close enough ('tirppur', 'tiurpur', 'turupur' → tirupur)."""
	from difflib import SequenceMatcher

	if not key:
		return False
	if key in candidates:
		return True
	if len(key) >= 4 and any(c.startswith(key) for c in candidates):
		return True
	# extra words after the name: 'Erode district', 'Salem Steel', 'Tiruppur North'
	if any(len(c) >= 5 and key.startswith(c) for c in candidates):
		return True
	return len(key) >= 5 and any(SequenceMatcher(None, key, c).ratio() >= ratio for c in candidates)


def territory_zone(state, city):
	"""KONGU / ROTN / ROI — the Ionic page's rule (Tamil Nadu + a KONGU city →
	KONGU; rest of Tamil Nadu or Kerala → ROTN; everything else → ROI), made
	tolerant of how states and cities are actually typed at the gate.

	A KONGU city counts as KONGU unless the state is clearly another state —
	blank, misspelt ('Thamilnagu') or the city typed into the state box all
	still land in KONGU. City and ROTN-state lists come from Visitor Settings."""
	s = get_settings()
	kongu = {place_key(c) for c in (s.kongu_cities or "").splitlines() if c.strip()}
	rotn = {place_key(c) for c in (s.rotn_states or "").splitlines() if c.strip()} | {TN, KL}
	st, ct = place_key(state), place_key(city)

	is_tn = st == "tn" or fuzzy_in(st, {TN})
	other_state = not is_tn and st in OTHER_STATES
	if fuzzy_in(ct, kongu) and not other_state:
		return "KONGU"
	if is_tn or st == "kl" or fuzzy_in(st, rotn):
		return "ROTN"
	return "ROI"


def zone_head(zone):
	s = get_settings()
	return {"KONGU": s.kongu_sales_person, "ROTN": s.rotn_sales_person}.get(zone) or s.roi_sales_person


# ── Lookups ──────────────────────────────────────────────────────────────────
def contact_by_mobile(ten):
	if not ten:
		return None
	rows = frappe.db.sql(
		"""select c.name from `tabContact` c
		   left join `tabContact Phone` p on p.parent = c.name and p.parenttype = 'Contact'
		   where c.mobile_no like %(m)s or p.phone like %(m)s
		   order by c.modified desc limit 1""",
		{"m": f"%{ten}"},
	)
	return rows[0][0] if rows else None


def customer_of_contact(contact):
	return frappe.db.get_value(
		"Dynamic Link",
		{"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"},
		"link_name",
	)


def first_sales_person(customer):
	return frappe.db.get_value(
		"Sales Team", {"parenttype": "Customer", "parent": customer}, "sales_person", order_by="idx asc"
	)


def user_of_sales_person(sales_person):
	if not sales_person:
		return None
	emp = frappe.db.get_value("Sales Person", sales_person, "employee")
	return frappe.db.get_value("Employee", emp, "user_id") if emp else None


def find_customer(mobile, company_name=None):
	"""Port of /api/getCustomerByMobile. Mobile match via Contact first,
	then exact customer_name match on the (upper-cased) company name."""
	ten = normalize_mobile(mobile)
	contact = contact_by_mobile(ten)
	if contact:
		full_name = frappe.db.get_value("Contact", contact, "full_name") or frappe.db.get_value(
			"Contact", contact, "first_name"
		)
		cust = customer_of_contact(contact)
		if cust:
			c = frappe.db.get_value("Customer", cust, ["customer_name", "customer_group", "territory"], as_dict=True) or {}
			return {
				"status": "found", "matched_by": "mobile", "contact": contact, "full_name": full_name,
				"customer_id": cust, "customer_name": c.get("customer_name") or cust,
				"customer_group": c.get("customer_group"), "territory": c.get("territory"),
				"sales_person": first_sales_person(cust),
			}
		return {"status": "contact_only", "matched_by": "mobile", "contact": contact, "full_name": full_name}

	company = (company_name or "").strip().upper()
	if company:
		cust = frappe.db.get_value("Customer", {"customer_name": company}, "name")
		if cust:
			c = frappe.db.get_value("Customer", cust, ["customer_name", "customer_group", "territory"], as_dict=True)
			return {
				"status": "found", "matched_by": "company_name",
				"customer_id": cust, "customer_name": c.customer_name,
				"customer_group": c.customer_group, "territory": c.territory,
				"sales_person": first_sales_person(cust),
			}
	return {"status": "not_found"}


def create_contact(first_name, ten, customer=None):
	doc = frappe.get_doc({
		"doctype": "Contact",
		"first_name": (first_name or "Unknown").strip().upper(),
		"status": "Passive",
		"phone_nos": [{"phone": f"91{ten}", "is_primary_mobile_no": 1, "is_primary_phone": 0}],
		"links": [{"link_doctype": "Customer", "link_name": customer}] if customer else [],
	})
	doc.insert(ignore_permissions=True)
	return doc.name


def create_customer_for_visitor(vd, overrides=None):
	"""Port of /api/createCustomerFromVisitor: reuse a Customer matched by
	mobile/company, else create one, then always add a linked Contact."""
	o = frappe._dict(overrides or {})
	ten = normalize_mobile(vd.mobile_no)
	customer_name = (vd.company_name or vd.name1 or "Unknown").strip().upper()

	existing = None
	contact = contact_by_mobile(ten)
	if contact:
		existing = customer_of_contact(contact)
	if not existing:
		existing = frappe.db.get_value("Customer", {"customer_name": customer_name}, "name")

	created = False
	if existing:
		customer = existing
	else:
		group = o.customer_group or vd.get("customer_group") or frappe.db.get_value(
			"Customer Group", {"is_group": 0}, "name", order_by="name asc"
		)
		sp = o.sales_person or vd.get("sales_person")
		ctype = o.erpnext_customer_type or vd.get("erpnext_customer_type")
		cust = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": customer_name,
			"customer_type": ctype if ctype in ("Company", "Individual", "Partnership") else "Company",
			"customer_group": group,
			"territory": link_value_or_none("Customer", "territory", o.territory or vd.get("territory")) or "All Territories",
			"sales_team": [{"sales_person": sp, "allocated_percentage": 100}] if sp else [],
		})
		cust.insert(ignore_permissions=True)
		customer, created = cust.name, True

	contact_created = False
	if not (contact and customer_of_contact(contact) == customer):
		create_contact(vd.name1 or vd.company_name, ten, customer)
		contact_created = True

	return {
		"customer_id": customer,
		"customer_name": frappe.db.get_value("Customer", customer, "customer_name"),
		"customer_created": created,
		"customer_reused": not created,
		"contact_created": contact_created,
	}


# ── CRM Lead ─────────────────────────────────────────────────────────────────
def resolve_lead_owner(vd):
	"""Same priority as the Node server:
	1. Customer linked to the visitor's mobile → its first sales person
	2. Customer whose name == company name → its first sales person
	3. Department rule (Garments / Others) — also queues a WhatsApp alert
	4. Territory zone head (KONGU / ROTN / ROI)
	Returns (lead_owner_user, sales_person, whatsapp_number)."""
	ten = normalize_mobile(vd.mobile_no)
	found = find_customer(ten, vd.company_name)
	sp = found.get("sales_person") if found.get("status") == "found" else None
	owner = user_of_sales_person(sp)
	if owner:
		return owner, sp, None

	whatsapp = None
	for rule in get_settings().department_rules:
		if (rule.department or "").lower() == (vd.department or "").lower():
			whatsapp = rule.whatsapp_notify
			if rule.assign_to == "User" and rule.lead_owner:
				return rule.lead_owner, None, whatsapp
			if rule.sales_person:
				owner = user_of_sales_person(rule.sales_person)
				if owner:
					return owner, rule.sales_person, whatsapp
			break

	zone = territory_zone(vd.state, vd.city)
	head = zone_head(zone)
	return user_of_sales_person(head), head, whatsapp


def create_lead_for_visitor(visitor_name):
	"""Background job. Idempotent per Visitor Data row: a row that already has
	a crm_lead is skipped, so retries and double enqueues are harmless. A
	re-entry is a new Visitor Data row, so it gets its own lead (same as the
	per-idx lock the Node server ended up with)."""
	s = get_settings()
	if not cint(s.create_crm_lead):
		return

	# Row lock: two workers picking up the same visitor wait on each other
	# here, and the second one sees crm_lead already set.
	frappe.db.sql("select name from `tabVisitor Data` where name=%s for update", visitor_name)
	vd = frappe.get_doc("Visitor Data", visitor_name)
	if vd.get("crm_lead") or not wants_lead(vd.department):
		return
	ten = normalize_mobile(vd.mobile_no)
	first_name = (vd.name1 or "").strip().upper()
	if not ten or not first_name:
		return

	attempts = cint(vd.get("crm_lead_attempts")) + 1
	frappe.db.set_value("Visitor Data", vd.name, "crm_lead_attempts", attempts, update_modified=False)

	try:
		lead_name, whatsapp = _insert_lead(vd, s, ten, first_name)
	except Exception:
		# Roll back the half-made lead but keep the attempt count, so the
		# retry job gives up after MAX_LEAD_ATTEMPTS instead of looping.
		frappe.db.rollback()
		frappe.db.set_value("Visitor Data", vd.name, "crm_lead_attempts", attempts, update_modified=False)
		frappe.db.commit()
		frappe.log_error(title=f"Visitor App: CRM Lead for {vd.name} failed")
		return

	frappe.db.commit()
	if whatsapp:
		send_whatsapp_template(whatsapp, lead_name, vd.location)


def _insert_lead(vd, s, ten, first_name):
	owner, sales_person, whatsapp = resolve_lead_owner(vd)
	zone = territory_zone(vd.state, vd.city)
	source = {"HO": "Walk-in HO", "JV": "Walk-in JV"}.get(vd.location, "New")

	lead = frappe.get_doc({
		"doctype": "CRM Lead",
		"first_name": first_name,
		"mobile_no": vd.mobile_no,
		"status": "New",
		"source": link_value_or_none("CRM Lead", "source", source),
		"lead_owner": owner,
		"territory": link_value_or_none("CRM Lead", "territory", zone),
		"job_title": "N/A",
		"email": f"{ten}@noemail.local",
	})
	meta = frappe.get_meta("CRM Lead")
	# The company name typed at the gate is unverified, so it goes into
	# Temp Organization only. Organization stays empty until sales confirms
	# the real one. Organization is mandatory on erp.pranera.in (Property
	# Setter), so the lead is created without the mandatory check; Desk still
	# asks for it on the next manual save, which is the intended prompt.
	company = (vd.company_name or "").strip().upper()
	if meta.has_field("custom_temp_organization"):
		lead.custom_temp_organization = company
		lead.flags.ignore_mandatory = True
	else:
		# Field missing (migrate not run yet) — keep the old behaviour rather
		# than lose the company name.
		lead.organization = company
	if meta.has_field("custom_location"):
		lead.custom_location = vd.location
	if meta.has_field("custom_lead_temperature"):
		lead.custom_lead_temperature = s.lead_temperature or "Hot"
	lead.insert(ignore_permissions=True)

	# Write the assignment back onto the visit. The Node app only put it on
	# the lead, which is why 40k Visitor Data rows have no sales person.
	# A guard/sales edit that already set a value is never overwritten.
	updates = {"crm_lead": lead.name}
	if sales_person and not vd.get("sales_person") and frappe.db.exists("Sales Person", sales_person):
		updates["sales_person"] = sales_person
	if not vd.get("territory"):
		terr = link_value_or_none("Visitor Data", "territory", zone)
		if terr:
			updates["territory"] = terr
	frappe.db.set_value("Visitor Data", vd.name, updates, update_modified=False)

	if not contact_by_mobile(ten):
		try:
			create_contact(first_name, ten)
		except Exception:
			frappe.log_error(title=f"Visitor App: contact for {vd.name}")

	return lead.name, whatsapp


def enqueue_lead(visitor_name):
	frappe.enqueue(
		"pranera_visitor.crm.create_lead_for_visitor",
		visitor_name=visitor_name,
		queue="short",
		enqueue_after_commit=True,
		job_id=f"visitor_lead::{visitor_name}",
		deduplicate=True,
	)


# ── WhatsApp ─────────────────────────────────────────────────────────────────
def _wa_number(phone):
	d = "".join(ch for ch in str(phone) if ch.isdigit())
	if len(d) == 10:
		return "91" + d
	if len(d) == 11 and d.startswith("0"):
		return "91" + d[1:]
	return d


def send_whatsapp_template(to_phone, lead_name, location):
	s = get_settings()
	if not cint(s.enable_whatsapp) or not s.whatsapp_phone_id:
		return
	token = s.get_password("whatsapp_token", raise_exception=False)
	if not token:
		return
	crm_link = f"{frappe.utils.get_url()}/crm/leads/{lead_name}?viewType=list#data"
	url = f"https://graph.facebook.com/{s.whatsapp_api_version or 'v22.0'}/{s.whatsapp_phone_id}/messages"
	body = {
		"messaging_product": "whatsapp",
		"to": _wa_number(to_phone),
		"type": "template",
		"template": {
			"name": s.whatsapp_template or "visitor_checkin_unassigned",
			"language": {"code": "en"},
			"components": [{
				"type": "body",
				"parameters": [
					{"type": "text", "text": lead_name},
					{"type": "text", "text": crm_link},
					{"type": "text", "text": location or "N/A"},
				],
			}],
		},
	}
	try:
		r = requests.post(url, json=body, headers={"Authorization": f"Bearer {token}"}, timeout=15)
		if r.status_code >= 300:
			frappe.log_error(title="Visitor App: WhatsApp send failed", message=r.text[:1000])
	except Exception:
		frappe.log_error(title="Visitor App: WhatsApp send error")
