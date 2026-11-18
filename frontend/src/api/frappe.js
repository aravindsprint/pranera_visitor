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

// ── Device token ──────────────────────────────────────────────────────────
// The gate tablet keeps the guard's API key:secret (from get_device_token)
// and sends it on every call. Frappe drops cookie sessions now and then —
// every `bench migrate` logs out whoever is polling at that moment — and
// without this the gate fell to "Login to access … not whitelisted".
const TOKEN_KEY = 'VISITOR_DEVICE_TOKEN'

export function getDeviceToken() {
  try {
    const t = JSON.parse(localStorage.getItem(TOKEN_KEY) || 'null')
    return t && t.user && t.token ? t : null
  } catch { return null }
}

export function setDeviceToken(t) {
  try {
    if (t && t.user && t.token) localStorage.setItem(TOKEN_KEY, JSON.stringify({ user: t.user, token: t.token }))
    else localStorage.removeItem(TOKEN_KEY)
  } catch { /* storage unavailable */ }
}

export function clearDeviceToken() { setDeviceToken(null) }

function cookieUser() {
  const u = decodeURIComponent(getCookieValue('user_id') || '')
  return u && u !== 'Guest' ? u : ''
}

// Who this device is working as: the cookie session if there is one,
// otherwise the stored token's user. A different user logged in through
// the cookie (e.g. an admin in Desk on the same browser) wins and the old
// token is dropped — Frappe rejects a token for another user than the session.
export function sessionUser() {
  const c = cookieUser()
  const t = getDeviceToken()
  if (c && t && t.user !== c) { clearDeviceToken(); return c }
  return c || t?.user || 'Guest'
}

function authHeaders() {
  const t = getDeviceToken()
  return t ? { Authorization: `token ${t.token}` } : {}
}

export async function initCSRF() {
  window.__FRAPPE_SESSION__ = { user: sessionUser(), base_url: '' }
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
  // The token itself was refused (secret rotated / user disabled) — drop it.
  clearDeviceToken()
  if (window.__FRAPPE_SESSION__) window.__FRAPPE_SESSION__.user = 'Guest'
  if (_authEventFired) return
  _authEventFired = true
  try { window.dispatchEvent(new Event('visitor:auth-required')) } catch { /* ignore */ }
}

async function handle(res, sentToken = false) {
  signalServerReachable(res)
  let data = {}
  try { data = await res.json() } catch { /* non-JSON (gateway error page) */ }
  if (!res.ok || data.exc) {
    const gateway = [502, 503, 504].includes(res.status)
    const message = extractServerError(data, res.statusText || 'Request failed')
    // With a token, a 403 "not permitted" is a real permission error, not
    // a lost session — only a 401 means the token was refused.
    const auth = sentToken ? res.status === 401 : isAuthFailure(res, data, message)
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
  const auth = authHeaders()
  let res
  try {
    res = await fetch(`/api/method/${method}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-Frappe-CSRF-Token': token, ...auth },
      body: encodeArgs(args).toString(),
      credentials: 'include'
    })
  } catch (e) {
    throw new ApiError('No connection to the server', { network: true })
  }
  return handle(res, !!auth.Authorization)
}

// Reads — GET, so the service worker's NetworkFirst cache can serve the
// last answer when the gate's Wi-Fi drops.
export async function get(method, args = {}) {
  const auth = authHeaders()
  let res
  try {
    res = await fetch(`/api/method/${method}?${encodeArgs(args)}`, { headers: auth, credentials: 'include' })
  } catch (e) {
    throw new ApiError('No connection to the server', { network: true })
  }
  return handle(res, !!auth.Authorization)
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
