# Deploying pranera_visitor

## 1. Install
```bash
cd ~/frappe-bench
bench get-app https://github.com/aravindsprint/pranera_visitor.git
bench --site erp.pranera.in install-app pranera_visitor
bench --site erp.pranera.in migrate      # custom fields on Visitor Data + settings seed
bench build --app pranera_visitor && bench restart
```

## 2. Configure (Desk → Visitor Settings)
1. **Gate Users**: add each guard's user with HO or JV. Tick *Can View All Locations* for admins.
2. Give those users the **Visitor Gate** role.
3. Check the seeded territory heads, KONGU cities and department rules.
4. **WhatsApp**: enter the Phone Number ID and Access Token, then tick *Enable*.
5. **Long stay email**: needs a default outgoing Email Account on the site.

## 3. Cut over from the Node server
In `sqlapp`, stop the visitor crons (`postVisitorData`, `syncMissingCrmLeads`). Otherwise both systems create leads. Keep the attendance crons running.

## Rebuilding the frontend
```bash
cd apps/pranera_visitor/frontend && npm install && npm run build   # writes ../pranera_visitor/public/visitor_app
cd ~/frappe-bench && bench build --app pranera_visitor && bench restart
```
`bench build` does not run Vite. Always run `npm run build` first and commit `public/visitor_app`.

## Local dev
`npm run dev` → http://localhost:3000/visitor-app (proxied to erp.pranera.in; set `VITE_BACKEND=http://127.0.0.1:8001` to use the local bench).
