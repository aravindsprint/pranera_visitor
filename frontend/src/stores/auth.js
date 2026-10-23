// src/stores/auth.js — Pranera Visitor App
// Frappe session login (same flow as pranera_roll). Instead of an Employee
// record check, access comes from get_boot: the Visitor Gate role + the
// user's gate (HO / JV) in Visitor Settings → Gate Users.
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getBoot, ensureCSRF, resetCSRF } from '@/api/frappe'
import { cacheGet, cacheSet } from '@/db'

const LOC_KEY = 'VISITOR_ADMIN_LOCATION'

export const useAuthStore = defineStore('auth', () => {
  const frappeUser = ref(window.__FRAPPE_SESSION__?.user || '')
  const isLoggedIn = ref(!!frappeUser.value && frappeUser.value !== 'Guest')
  const boot       = ref(null)
  const loading    = ref(false)
  const error      = ref('')
  // Admins (can_view_all) pick the gate they're working; remembered per device.
  const adminLocation = ref(localStorage.getItem(LOC_KEY) || '')

  const fullName    = computed(() => boot.value?.full_name || frappeUser.value)
  const canViewAll  = computed(() => !!boot.value?.can_view_all)
  // Gate used for new check-ins. '' means an admin hasn't picked one yet.
  const location    = computed(() => boot.value?.location || (canViewAll.value ? adminLocation.value : ''))
  // Filter for lists/reports. '' (admin, no pick) = all gates.
  const viewLocation = computed(() => canViewAll.value ? adminLocation.value : (boot.value?.location || ''))

  function refreshSession() {
    const u = window.__FRAPPE_SESSION__?.user || ''
    frappeUser.value = u
    isLoggedIn.value = !!u && u !== 'Guest'
  }

  function setAdminLocation(loc) {
    adminLocation.value = loc || ''
    try { localStorage.setItem(LOC_KEY, adminLocation.value) } catch { /* ignore */ }
  }

  async function loadBoot() {
    loading.value = true
    error.value = ''
    try {
      const b = await getBoot()
      if (b.user !== frappeUser.value) throw new Error('Session changed — please log in again')
      boot.value = b
      await cacheSet(`boot:${b.user}`, b)
      if (!b.is_mapped) error.value = "Your user isn't mapped to a gate. Ask an admin to add you in Visitor Settings → Gate Users."
      return true
    } catch (err) {
      // Offline start: fall back to the last boot for this same user.
      const cached = await cacheGet(`boot:${frappeUser.value}`)
      if (cached && err.network) { boot.value = cached; return true }
      error.value = err.message || 'Failed to load the Visitor App'
      return false
    } finally {
      loading.value = false
    }
  }

  async function login(email, password) {
    loading.value = true
    error.value = ''
    try {
      const res = await fetch('/api/method/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ usr: email, pwd: password }).toString(),
        credentials: 'include'
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok || data.message !== 'Logged In') {
        let msg = 'Incorrect email or password'
        try {
          const msgs = JSON.parse(data._server_messages || '[]')
          if (msgs.length) msg = JSON.parse(msgs[msgs.length - 1]).message || msg
        } catch { /* keep default */ }
        throw new Error(msg)
      }
      return true
    } catch (err) {
      error.value = err.message || 'Login failed'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    try {
      const token = await ensureCSRF()
      await fetch('/api/method/frappe.auth.logout', {
        method: 'POST', headers: { 'X-Frappe-CSRF-Token': token }, credentials: 'include'
      })
    } catch (_) { /* still clear local state */ }
    resetCSRF()
    boot.value = null
    if (window.__FRAPPE_SESSION__) window.__FRAPPE_SESSION__.user = 'Guest'
    frappeUser.value = 'Guest'
    isLoggedIn.value = false
  }

  return {
    frappeUser, isLoggedIn, boot, loading, error,
    fullName, canViewAll, location, viewLocation, adminLocation,
    refreshSession, setAdminLocation, loadBoot, login, logout,
  }
})
