"""CRM Lead / Contact / Customer logic — port of triggerCrmLeadCreation,
getCustomerByMobile and createCustomerFromVisitor from the Node server.

Runs inside Frappe now, so it uses the DB directly instead of REST calls
with a hardcoded API token.
"""
import re

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


# Reference data, not configuration: the names of India's states and union territories, so the City
# dropdown can tell a state in CRM Territory (Kerala) from a district (Ernakulam).
INDIA_STATES = {
	place_key(x)
	for x in (
		"Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
		"Chandigarh", "Chhattisgarh", "Chattishgarh", "Dadra and Nagar Haveli and Daman and Diu",
		"Dadra and Nagar Haveli", "Daman and Diu", "Delhi", "Goa", "Gujarat", "Haryana",
		"Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh",
		"Lakshadweep", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
		"Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
		"Uttar Pradesh", "Uttarakhand", "West Bengal",
	)
}


def _closest(key, names, ratio=0.8):
	"""The name in `names` ({place key: name}) that `key` means, allowing gate-typing slips: exact,
	a 4+ letter prefix of one name only ('coim' → Coimbatore), extra words after the name ('Erode
	district'), or close enough ('tirppur' → Tiruppur). None when nothing is close."""
	from difflib import SequenceMatcher

	if not key:
		return None
	if key in names:
		return names[key]
	if len(key) >= 4:
		starts = [n for k, n in names.items() if k.startswith(key)]
		if len(starts) == 1:
			return starts[0]
	longest = max((k for k in names if len(k) >= 5 and key.startswith(k)), key=len, default=None)
	if longest:
		return names[longest]
	if len(key) < 5:
		return None
	score, best = max(((SequenceMatcher(None, key, k).ratio(), n) for k, n in names.items()), default=(0, None))
	return best if score >= ratio else None


def _tree() -> dict:
	"""CRM Territory as {name: row(parent, manager, is_group)}; empty without Frappe CRM."""
	if not frappe.db.exists("DocType", "CRM Territory"):
		return {}
	rows = frappe.get_all(
		"CRM Territory",
		fields=["name", "parent_crm_territory as parent", "territory_manager as manager", "is_group"],
	)
	return {r.name: r for r in rows}


def _chain(tree, name) -> list:
	"""The territory and its parents, up to the root."""
	out = []
	while name and name in tree and name not in out:
		out.append(name)
		name = tree[name].parent
	return out


def _zone(tree, name) -> str:
	"""The territory's zone: its group just below the root of the tree (KONGU, ROTN, ROI, ... as the
	tree has them). A zone is its own zone; the root has none."""
	chain = _chain(tree, name)
	return chain[-2] if len(chain) >= 2 else ""


def visitor_territory(state, city, tree=None) -> str | None:
	"""The CRM Territory a visitor belongs to: the one named like the city, else like the state
	(spelling tolerant), else Visitor Settings → Default Territory. The city wins when both match:
	the tree may group districts by zone, not by state. A town that is not a district goes in CRM
	Territory under its district or zone."""
	tree = tree if tree is not None else _tree()
	names = {}
	for name, row in tree.items():
		if row.parent:  # the root (All Territories) is nobody's territory
			names.setdefault(place_key(name), name)
	for text in (city, state):
		found = _closest(place_key(text), names)
		if found:
			return found
	default = get_settings().default_territory
	return default if default in tree else None


def territory_zone(state, city) -> str:
	"""The visitor's zone (the top-level group of their territory in CRM Territory), or ""."""
	tree = _tree()
	return _zone(tree, visitor_territory(state, city, tree))


def territory_manager(state, city) -> str | None:
	"""The user who gets a new visitor's lead: the Territory Manager of the visitor's territory,
	going up the tree to the first one that is set."""
	tree = _tree()
	return next(
		(tree[n].manager for n in _chain(tree, visitor_territory(state, city, tree)) if tree[n].manager),
		None,
	)


def _home_state() -> tuple[str, set]:
	settings = get_settings()
	zones = {z.strip() for z in (settings.home_state_zones or "").splitlines() if z.strip()}
	return (settings.home_state or "").strip(), zones


def _state_of(tree, name, is_state, home, home_zones) -> str | None:
	"""The state a territory is in: the state above it in CRM Territory, else the Home State when it
	sits under one of the Home State Zones."""
	for node in _chain(tree, name)[1:]:
		if node in is_state:
			return node
	return home if home and _zone(tree, name) in home_zones else None


def _is_place(tree, name, is_state) -> bool:
	"""A district or town: not the root, a zone, a state or a group."""
	row = tree.get(name)
	return bool(row) and bool(row.parent) and not row.is_group and name not in is_state and _zone(tree, name) != name


def city_options() -> dict:
	"""{state: [cities]} for the gate's City dropdown, from CRM Territory. A territory under a state
	(Kerala → Ernakulam) belongs to that state. One under a zone listed in Visitor Settings → Home
	State Zones (KONGU → Tiruppur) belongs to Visitor Settings → Home State. States without districts
	get no list (the gate types the city)."""
	tree = _tree()
	home, home_zones = _home_state()
	is_state = {n for n in tree if place_key(n) in INDIA_STATES}
	options = {}
	for name in tree:
		if not _is_place(tree, name, is_state):
			continue
		state = _state_of(tree, name, is_state, home, home_zones)
		if state:
			options.setdefault(state, set()).add(name)
	return {state: sorted(cities) for state, cities in options.items()}


def known_place(customer=None, lead_territory=None) -> tuple[str, str]:
	"""(state, city) of an existing customer or lead, as CRM Territory names, or ("", ""): the
	customer's territory, else the city on one of its addresses ('TIRUPUR-641608' → Tiruppur), else
	the lead's territory when it is a district (a zone such as KONGU names no city)."""
	tree = _tree()
	is_state = {n for n in tree if place_key(n) in INDIA_STATES}
	names = {place_key(n): n for n in tree if _is_place(tree, n, is_state)}
	candidates = []  # (place text, state written with it)
	if customer:
		candidates.append((frappe.db.get_value("Customer", customer, "territory"), ""))
		addresses = frappe.get_all(
			"Dynamic Link",
			filters={"link_doctype": "Customer", "link_name": customer, "parenttype": "Address"},
			pluck="parent",
		)
		if addresses:
			candidates += frappe.get_all(
				"Address", filters={"name": ["in", addresses]}, fields=["city", "state"], as_list=True
			)
	if lead_territory:
		candidates.append((lead_territory, ""))
	home, home_zones = _home_state()
	for text, state in candidates:
		# an address city often carries the PIN code: 'TIRUPUR-641608', 'Tirupur - 641 604'
		city = _closest(place_key(re.split(r"[-,0-9]", text or "")[0]), names)
		if city:
			return _state_of(tree, city, is_state, home, home_zones) or (state or ""), city
	return "", ""


def latest_lead(ten, with_organization=False):
	"""The visitor's most recent CRM Lead by mobile (with an organization filled in, if asked)."""
	filters = {"mobile_no": ["like", f"%{ten}"]}
	if with_organization:
		filters["organization"] = ["is", "set"]
	rows = frappe.get_all(
		"CRM Lead",
		filters=filters,
		fields=["name", "first_name", "organization", "custom_temp_organization", "territory"]
		if frappe.get_meta("CRM Lead").has_field("custom_temp_organization")
		else ["name", "first_name", "organization", "territory"],
		order_by="creation desc",
		limit=1,
	)
	return rows[0] if rows else None


def existing_visitor(ten) -> dict | None:
	"""What the CRM already knows about a mobile number at the gate: an existing customer (by its
	contact) or an existing CRM lead. Returns the name, company, organization and place to fill the
	check-in with, or None for a new visitor."""
	found = find_customer(ten)
	lead = latest_lead(ten)
	if found.get("status") != "found" and not lead:
		return None
	with_org = latest_lead(ten, with_organization=True)
	organization = (
		found.get("customer_name") if found.get("status") == "found" else (with_org or {}).get("organization")
	)
	state, city = known_place(found.get("customer_id"), (lead or {}).get("territory"))
	return {
		"kind": "customer" if found.get("status") == "found" else "lead",
		"customer": found.get("customer_id"),
		"lead": (lead or {}).get("name"),
		"name": found.get("full_name") or (lead or {}).get("first_name") or "",
		"company": organization or (lead or {}).get("custom_temp_organization") or "",
		"organization": organization or "",
		"state": state,
		"city": city,
	}


def erpnext_territory(zone):
	"""Visitor Data's Territory for a CRM zone. The field links to ERPNext's Territory list, which may
	name a zone differently (CRM "ROI" is ERPNext "Rest of India"): Visitor Settings → ERPNext
	Territory for each zone pairs them, else the zone's own name is used. None when ERPNext has no
	such territory."""
	if not zone:
		return None
	mapped = next(
		(row.erpnext_territory for row in get_settings().get("zone_territories") or [] if row.zone == zone),
		None,
	)
	return link_value_or_none("Visitor Data", "territory", mapped or zone)


def sales_person_of_user(user):
	"""The enabled Sales Person whose Employee is this user, if any."""
	if not user:
		return None
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not employee:
		return None
	return frappe.db.get_value("Sales Person", {"employee": employee, "enabled": 1}, "name")


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
	"""Who gets the visitor's lead:
	1. An existing customer (by the visitor's mobile, else by company name) → its first sales
	   person, when that sales person has a CRM user.
	2. Otherwise (a new customer, or one without such a sales person): a matching Department Rule in
	   Visitor Settings, which may also queue a WhatsApp alert.
	3. Otherwise the Territory Manager in CRM Territory of the visitor's territory (or the first
	   one set above it).
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
				return rule.lead_owner, sales_person_of_user(rule.lead_owner), whatsapp
			if rule.sales_person:
				owner = user_of_sales_person(rule.sales_person)
				if owner:
					return owner, rule.sales_person, whatsapp
			break

	owner = territory_manager(vd.state, vd.city)
	return owner, sales_person_of_user(owner), whatsapp


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


def default_lead_status():
	"""First CRM Lead Status by position. erp.pranera.in replaced the stock
	statuses ("New" doesn't exist there; the first one is "New Enquiry"), so a
	hardcoded "New" failed link validation on every insert."""
	if frappe.db.exists("CRM Lead Status", "New"):
		return "New"
	return frappe.db.get_value("CRM Lead Status", {}, "name", order_by="position asc")


def _insert_lead(vd, s, ten, first_name):
	owner, sales_person, whatsapp = resolve_lead_owner(vd)
	zone = territory_zone(vd.state, vd.city)
	source = {"HO": "Walk-in HO", "JV": "Walk-in JV"}.get(vd.location, "New")

	lead = frappe.get_doc({
		"doctype": "CRM Lead",
		"first_name": first_name,
		"mobile_no": vd.mobile_no,
		"status": default_lead_status(),
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
	organization = _known_organization(ten, vd.company_name)
	if organization:
		# an existing customer or lead: its real organization, not the typed name
		lead.organization = organization
	elif meta.has_field("custom_temp_organization"):
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
	# The contact first: a lead saved with an Organization puts the contact with its mobile under
	# that organization and customer (Pranera CRM, lead_contact.py), so it has to exist already.
	if not contact_by_mobile(ten):
		try:
			create_contact(first_name, ten)
		except Exception:
			frappe.log_error(title=f"Visitor App: contact for {vd.name}")
	lead.insert(ignore_permissions=True)

	# Write the assignment back onto the visit. The Node app only put it on
	# the lead, which is why 40k Visitor Data rows have no sales person.
	# A guard/sales edit that already set a value is never overwritten.
	updates = {"crm_lead": lead.name}
	if sales_person and not vd.get("sales_person") and frappe.db.exists("Sales Person", sales_person):
		updates["sales_person"] = sales_person
	if not vd.get("territory"):
		terr = erpnext_territory(zone)
		if terr:
			updates["territory"] = terr
	frappe.db.set_value("Visitor Data", vd.name, updates, update_modified=False)
	return lead.name, whatsapp


def _known_organization(ten, company_name):
	"""The organization of an existing customer (by mobile, else by company name) or of the
	visitor's earlier lead, for CRM Lead → Organization. None for a new visitor. When Organization
	is a link (Frappe CRM's default), only an existing CRM Organization is used."""
	found = find_customer(ten, company_name)
	if found.get("status") == "found":
		organization = found.get("customer_name")
	else:
		organization = (latest_lead(ten, with_organization=True) or {}).get("organization")
	if not organization:
		return None
	return link_value_or_none("CRM Lead", "organization", organization)


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
