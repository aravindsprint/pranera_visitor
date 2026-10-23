
app_name        = "pranera_visitor"
app_title       = "Pranera Visitor"
app_publisher   = "Pranera Services & Solutions"
app_description = "Gate visitor check-in / check-out app for ERPNext"
app_email       = "admin@pranera.in"
app_license     = "MIT"
app_version     = "1.0.0"

# Visitor Data is owned by the Textiles And Garments app. This app only adds
# custom fields to it (see install.py), a settings doctype, the gate-side API
# and the PWA front-end — the same split pranera_roll uses for Roll.
required_apps = ["erpnext"]

add_to_apps_screen = [
    {
        "name": "pranera_visitor",
        "logo": "/assets/pranera_visitor/images/logo.svg",
        "title": "Visitor App",
        "route": "/visitor-app",
    }
]

website_route_rules = [
    {"from_route": "/visitor-app/<path:app_path>", "to_route": "visitor-app"},
]

# Custom fields on Visitor Data are (re)applied on every migrate — idempotent.
after_install = "pranera_visitor.install.after_install"
after_migrate = "pranera_visitor.install.after_migrate"

# Replaces the Node server's crons:
#   */2  syncMissingCrmLeads    → retry_missing_crm_leads
#   1-min frontend email timer  → send_long_stay_alerts (server-side, once per visit)
# The Node visitor sync cron (postVisitorData) has no replacement — the app
# writes Visitor Data directly, so there is nothing to sync.
scheduler_events = {
    "cron": {
        "*/5 * * * *": [
            "pranera_visitor.tasks.send_long_stay_alerts",
            "pranera_visitor.tasks.retry_missing_crm_leads",
        ],
    },
}

fixtures = [
    {"doctype": "Role", "filters": [["name", "in", ["Visitor Gate"]]]},
]
