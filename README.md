# Pranera Visitor

Gate visitor check-in / check-out app for erp.pranera.in. Built the same way as `pranera_roll`: a Vue 3 + Vite PWA served by Frappe at `/visitor-app`.

It replaces the Ionic visitor app and the visitor half of the Node server (`sqlapp`). **Visitor Data** is the single source of truth: no SQLite and no sync crons.

| Page | What it does |
|---|---|
| Visitor Data | Mobile + department → new / known (prefilled) / same-day re-entry / already inside. Active list with live duration, long-stay highlight, Exit, and an Edit sheet with customer lookup/create. Works offline (IndexedDB queue). |
| Visitor Report | Date range, gate, department and status filters, plus summary tiles, a detail sheet and CSV export. |
| Security Scanned Report | Sales Invoices and Stock Entries with `security_passed` / scanned date / scan point, plus CSV export. |

Server side:
- `api/visitor.py` is the whitelisted API.
- `crm.py` creates the CRM Lead, Contact and Customer, and sends the WhatsApp alert.
- `tasks.py` sends the long-stay email and retries missing leads (every 5 min).
- **Visitor Settings** holds the gate users and the rules that were hardcoded in Node.
