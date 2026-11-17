// src/api/frappe.js — Pranera Visitor App
// Same Frappe session + CSRF layer as pranera_roll. All visitor logic lives
// in pranera_visitor/api/visitor.py — no Node server, no hardcoded tokens.

function signalServerReachable(res) {
  const s = res && res.status
  if (s && s !== 502 && s !== 503 && s !== 504) {
    try { window.dispatchEvent(new Event('visitor:api-ok')) } catch { /* ignore */ }
  }
}

// ── CSRF ──────────────────────────────────────────────────────────────────
let _csrf = ''

function getCookieValue(name) {
  return document.cookie.split('; ').find(r => r.startsWith(name + '='))?.split('=')[1] || ''
}

export async function ensureCSRF() {
  if (_csrf) return _csrf
  // Injected by www/visitor_app.py. Ignore an unrendered "{{ csrf_token }}".
  if (window.csrf_token && !String(window.csrf_token).includes('{{')) { _csrf = window.csrf_token; return _csrf }
  const cookie = getCookieValue('csrftoken') || getCookieValue('X-Frappe-CSRF-Token')
  if (cookie) { _csrf = cookie; return _csrf }
  // Offline-cached shell or dev proxy: ask the app for one.
  try {
    const r = await fetch('/api/method/pranera_visitor.api.visitor.get_csrf_token', { credentials: 'include' })
    if (r.ok) {
      const d = await r.json()
      if (d?.message) { _csrf = d.message; window.csrf_token = d.message }
    }
  } catch { /* offline */ }
  return _csrf
}

export function resetCSRF() {
  _csrf = ''
  window.csrf_token = ''
}

export async function initCSRF() {
  window.__FRAPPE_SESSION__ = {
    user: decodeURIComponent(getCookieValue('user_id') || '') || 'Guest',
    base_url: ''
  }
  await ensureCSRF()
  window.__FRAPPE_SESSION__.csrf_token = _csrf
}

export function isLoggedIn() {
  const user = window.__FRAPPE_SESSION__?.user
  return !!user && user !== 'Guest'
}

// ── Error extraction (short message instead of a traceback) ──────────────
function extractServerError(data, fallback = 'Request failed') {
  try {
    const msgs = JSON.parse(data._server_messages || '[]')
    if (msgs.length) {
      const last = JSON.parse(msgs[msgs.length - 1])
      const text = String(last.message || last).replace(/<[^>]+>/g, '').trim()
      if (text) return text
    }
  } catch { /* fall through */ }
  if (data.exception) {
    const parts = String(data.exception).split(':')
    return (parts.length > 1 ? parts.slice(1).join(':') : parts[0]).trim()
  }
  if (data.exc) {
    try {
      const tb = JSON.parse(data.exc)
      const lines = String(tb[0] || '').trim().split('\n')
      return lines[lines.length - 1].trim()
    } catch { /* fall through */ }
  }
  return fallback
}

export class ApiError extends Error {
  constructor(message, { status = 0, network = false, auth = false } = {}) {
    super(message)
    this.status = status
    // true = the request never got an answer (offline / timeout) → safe to queue
    this.network = network
    // true = the server treated us as Guest (session expired / logged out on
    // the server). The request itself was fine — keep it and log in again.
    this.auth = auth
  }
}

// Frappe answers an expired session with 403 PermissionError "You are not
// permitted to access this resource. Login to access" + "not whitelisted"
// (the session silently became Guest), or 401 / SessionExpired.
const AUTH_ERROR_RE = /login to access|not whitelisted|session expired|sessionexpired/i

export function isAuthErrorText(text) {
  return AUTH_ERROR_RE.test(String(text || ''))
}

function isAuthFailure(res, data, message) {
  if (res.status === 401) return true
  if (data?.exc_type === 'SessionExpired') return true
  return res.status === 403 && isAuthErrorText(message)
}

// Tell the app the server no longer knows us, so it can mark the session as
// Guest and send the guard to the login page. Fired at most once per page.
let _authEventFired = false
function signalAuthRequired() {
  resetCSRF()
  if (window.__FRAPPE_SESSION__) window.__FRAPPE_SESSION__.user = 'Guest'
  if (_authEventFired) return
  _authEventFired = true
  try { window.dispatchEvent(new Event('visitor:auth-required')) } catch { /* ignore */ }
}

async function handle(res) {
  signalServerReachable(res)
  let data = {}
  try { data = await res.json() } catch { /* non-JSON (gateway error page) */ }
  if (!res.ok || data.exc) {
    const gateway = [502, 503, 504].includes(res.status)
    const message = extractServerError(data, res.statusText || 'Request failed')
    const auth = isAuthFailure(res, data, message)
    if (auth) signalAuthRequired()
    throw new ApiError(auth ? 'Session expired — please log in again' : message, { status: res.status, network: gateway, auth })
  }
  return data.message
}

function encodeArgs(args) {
  const body = new URLSearchParams()
  for (const [k, v] of Object.entries(args)) {
    if (v === undefined || v === null) continue
    body.append(k, typeof v === 'object' ? JSON.stringify(v) : v)
  }
  return body
}

// Writes — POST with CSRF.
export async function call(method, args = {}) {
  const token = await ensureCSRF()
  let res
  try {
    res = await fetch(`/api/method/${method}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-Frappe-CSRF-Token': token },
      body: encodeArgs(args).toString(),
      credentials: 'include'
    })
  } catch (e) {
    throw new ApiError('No connection to the server', { network: true })
  }
  return handle(res)
}

// Reads — GET, so the service worker's NetworkFirst cache can serve the
// last answer when the gate's Wi-Fi drops.
export async function get(method, args = {}) {
  let res
  try {
    res = await fetch(`/api/method/${method}?${encodeArgs(args)}`, { credentials: 'include' })
  } catch (e) {
    throw new ApiError('No connection to the server', { network: true })
  }
  return handle(res)
}

// ── Visitor API ───────────────────────────────────────────────────────────
const V = 'pranera_visitor.api.visitor'

export const getBoot            = ()                        => get(`${V}.get_boot`)
export const lookupMobile       = (mobile_no)               => get(`${V}.lookup_mobile`, { mobile_no })
export const getActiveVisitors  = (location)                => get(`${V}.get_active_visitors`, { location })
export const checkIn            = (data, client_id)         => call(`${V}.check_in`, { data, client_id })
export const markExit           = (name, exited_at)         => call(`${V}.mark_exit`, { name, exited_at })
export const updateVisitor      = (name, data, linkContact) => call(`${V}.update_visitor`, { name, data, link_contact_to_customer: linkContact ? 1 : 0 })
export const lookupCustomer     = (name)                    => get(`${V}.lookup_customer`, { name })
export const createCustomer     = (name, data)              => call(`${V}.create_customer`, { name, data })
export const getVisitorReport   = (from_date, to_date, location) => get(`${V}.get_visitor_report`, { from_date, to_date, location })
export const getSecurityScanReport = (from_date, to_date, scanned_from) => get(`${V}.get_security_scan_report`, { from_date, to_date, scanned_from })
