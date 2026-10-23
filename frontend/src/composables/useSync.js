// src/composables/useSync.js — Pranera Visitor App
// Reachability probe from pranera_roll (navigator.onLine lies both ways)
// plus the offline queue that replaces the Ionic OfflineSyncService.
//
// Differences from the Ionic version:
//   * IndexedDB (Dexie) instead of localStorage
//   * each queued check-in carries a client_id; the server de-duplicates on
//     it, so a replay after a half-finished request never double-checks-in
//   * exits are queued too (the old app needed network to mark an exit)
//   * a queued item that the server *rejects* (validation error) is kept as
//     'failed' with the reason instead of being retried forever
import { ref, onMounted, onUnmounted } from 'vue'
import { db } from '@/db'
import { checkIn, markExit } from '@/api/frappe'

export const isOnline     = ref(navigator.onLine)
export const isSyncing    = ref(false)
export const pendingCount = ref(0)
export const failedItems  = ref([])

let reachTimer = null
let probeInFlight = null
const PROBE_URL = '/api/method/ping'
const PROBE_EVERY_ONLINE_MS = 15_000
const PROBE_EVERY_OFFLINE_MS = 4_000

export function newClientId() {
  const rnd = (crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`)
  return `VA-${rnd}`
}

export async function refreshQueueState() {
  try {
    pendingCount.value = await db.queue.where('status').equals('pending').count()
    failedItems.value  = await db.queue.where('status').equals('failed').toArray()
  } catch { /* IndexedDB unavailable */ }
}

export async function enqueue(type, payload, client_id = newClientId()) {
  await db.queue.add({ type, payload, client_id, status: 'pending', created_at: new Date().toISOString() })
  await refreshQueueState()
  checkReachable()   // flips the banner to offline right away (or flushes if it was a blip)
  return client_id
}

export async function dismissFailed(id) {
  await db.queue.delete(id)
  await refreshQueueState()
}

function setOnline(next) {
  if (isOnline.value === next) return
  isOnline.value = next
  if (next) flushQueue()
}

async function probeOnce() {
  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), 8000)
  try {
    const r = await fetch(`${PROBE_URL}?_=${Date.now()}`, { credentials: 'include', cache: 'no-store', signal: ctrl.signal })
    return !(r.status === 502 || r.status === 503 || r.status === 504)
  } catch {
    return false
  } finally {
    clearTimeout(t)
  }
}

export function checkReachable() {
  if (probeInFlight) return probeInFlight
  probeInFlight = probeOnce()
    .then(ok => {
      setOnline(ok)
      // Flush whenever the server answers — not only on an offline→online
      // flip. A single failed request queues an item without the probe ever
      // marking the app offline, so waiting for a flip would strand it.
      if (ok) flushQueue()
      return ok
    })
    .finally(() => { probeInFlight = null })
  return probeInFlight
}

export async function flushQueue() {
  if (!isOnline.value || isSyncing.value) return
  isSyncing.value = true   // claim before the first await so overlapping calls bail out
  let synced = 0
  try {
    const items = await db.queue.where('status').equals('pending').sortBy('id')
    for (const item of items) {
      try {
        if (item.type === 'check_in') {
          await checkIn(item.payload, item.client_id)
        } else if (item.type === 'exit') {
          // Exit for a check-in that was itself queued: resolve the real
          // Visitor Data name now that the check-in has synced.
          let name = item.payload.name
          if (!name && item.payload.check_in_client_id) {
            const res = await checkIn(item.payload.check_in_payload, item.payload.check_in_client_id)
            name = res?.visitor?.name
          }
          if (name) await markExit(name)
        }
        await db.queue.delete(item.id)
        synced++
      } catch (err) {
        if (err.network) break      // connection dropped again — try later
        await db.queue.update(item.id, { status: 'failed', error: err.message })
      }
    }
  } finally {
    isSyncing.value = false
    await refreshQueueState()
    if (synced) window.dispatchEvent(new CustomEvent('visitor:queue-synced', { detail: { synced } }))
  }
}

function onApiOk() { if (!isOnline.value) setOnline(true) }

function scheduleProbe() {
  clearTimeout(reachTimer)
  reachTimer = setTimeout(async () => {
    await checkReachable()
    if (isOnline.value) flushQueue()
    scheduleProbe()
  }, isOnline.value ? PROBE_EVERY_ONLINE_MS : PROBE_EVERY_OFFLINE_MS)
}

export function useSync() {
  const onNet  = () => checkReachable()
  const onWake = () => { if (document.visibilityState === 'visible') checkReachable() }

  onMounted(async () => {
    window.addEventListener('online', onNet)
    window.addEventListener('offline', onNet)
    window.addEventListener('focus', onWake)
    document.addEventListener('visibilitychange', onWake)
    window.addEventListener('visitor:api-ok', onApiOk)
    await refreshQueueState()
    await checkReachable()
    flushQueue()
    scheduleProbe()
  })

  onUnmounted(() => {
    window.removeEventListener('online', onNet)
    window.removeEventListener('offline', onNet)
    window.removeEventListener('focus', onWake)
    document.removeEventListener('visibilitychange', onWake)
    window.removeEventListener('visitor:api-ok', onApiOk)
    clearTimeout(reachTimer)
  })

  return { isOnline, isSyncing, pendingCount, failedItems, flushQueue }
}
