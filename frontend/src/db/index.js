// src/db/index.js — Pranera Visitor App
// Own IndexedDB database so it never clashes with the Knit / Roll PWAs on
// the same device.
//   queue — check-ins / exits made while offline, replayed by useSync
//   cache — last boot payload + active-visitor list, for an offline start
import Dexie from 'dexie'

export const db = new Dexie('PraneraVisitorDB')

db.version(1).stores({
  queue: '++id, client_id, type, status, created_at',
  cache: '&key',
})

export async function cacheSet(key, value) {
  try { await db.cache.put({ key, value, at: Date.now() }) } catch { /* private mode */ }
}
export async function cacheGet(key) {
  try { return (await db.cache.get(key))?.value ?? null } catch { return null }
}

export default db
