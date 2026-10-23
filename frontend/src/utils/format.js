// Frappe sends "YYYY-MM-DD HH:mm:ss" (site time = IST). Safari can't parse
// the space form, so swap it for "T" — read as device-local, which is IST
// at the gate.
export function parseFrappeDate(s) {
  if (!s) return null
  if (s instanceof Date) return s
  return new Date(String(s).replace(' ', 'T'))
}

export function pad(n) { return String(n).padStart(2, '0') }

export function toFrappeDatetime(d = new Date()) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

export function toISODate(d = new Date()) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function minutesSince(s, now = Date.now()) {
  const d = parseFrappeDate(s)
  return d ? Math.max(0, (now - d.getTime()) / 60000) : 0
}

export function hms(s, now = Date.now()) {
  const d = parseFrappeDate(s)
  if (!d) return ''
  const t = Math.max(0, Math.floor((now - d.getTime()) / 1000))
  return `${pad(Math.floor(t / 3600))}:${pad(Math.floor((t % 3600) / 60))}:${pad(t % 60)}`
}

export function fmtDateTime(s) {
  const d = parseFrappeDate(s)
  if (!d || isNaN(d)) return ''
  let h = d.getHours(); const ap = h >= 12 ? 'PM' : 'AM'; h = h % 12 || 12
  return `${pad(d.getDate())}-${pad(d.getMonth() + 1)}-${d.getFullYear()} ${pad(h)}:${pad(d.getMinutes())} ${ap}`
}

export function fmtTime(s) {
  const d = parseFrappeDate(s)
  if (!d || isNaN(d)) return ''
  let h = d.getHours(); const ap = h >= 12 ? 'PM' : 'AM'; h = h % 12 || 12
  return `${pad(h)}:${pad(d.getMinutes())} ${ap}`
}

export function fmtDate(s) {
  const d = parseFrappeDate(s)
  if (!d || isNaN(d)) return ''
  return `${pad(d.getDate())}-${pad(d.getMonth() + 1)}-${d.getFullYear()}`
}

export function normaliseMobile(raw) {
  const digits = String(raw || '').replace(/\D/g, '')
  if (digits.length === 12 && digits.startsWith('91')) return digits.slice(2)
  if (digits.length === 11 && digits.startsWith('0')) return digits.slice(1)
  return digits.slice(-10)
}

// CSV download for the report pages.
export function downloadCSV(filename, columns, rows) {
  const esc = v => {
    const s = v == null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = [columns.map(c => esc(c.label)).join(',')]
  for (const r of rows) lines.push(columns.map(c => esc(typeof c.value === 'function' ? c.value(r) : r[c.key])).join(','))
  const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}
