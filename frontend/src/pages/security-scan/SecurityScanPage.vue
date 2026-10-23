<template>
  <div class="page">
    <AppHeader title="Security Scanned Report" subtitle="Sales Invoices & Stock Entries" active="security-scan">
      <template #actions>
        <button class="icon-btn" :disabled="!currentRows.length" @click="exportCSV" title="Download CSV"><i class="pi pi-download"></i></button>
      </template>
    </AppHeader>

    <div class="page-content page-content--wide">
      <div class="card">
        <DateRange :from="from" :to="to" @change="onRange" />
        <div class="ss-filters">
          <select v-model="scannedFrom" class="form-input" @change="load">
            <option value="">All scan points</option>
            <option v-for="o in scanOptions" :key="o">{{ o }}</option>
          </select>
          <select v-model="status" class="form-input">
            <option value="">Passed + pending</option>
            <option value="Yes">Passed</option>
            <option value="No">Not passed</option>
          </select>
        </div>
      </div>

      <div class="tabs">
        <button v-for="t in tabs" :key="t.key" class="tab" :class="{ 'tab--on': tab === t.key }" @click="tab = t.key">
          <span>{{ t.label }}</span>
          <span class="tab__counts" v-if="summary[t.key]">
            <span class="badge badge-success">{{ summary[t.key].passed }} passed</span>
            <span class="badge badge-danger">{{ summary[t.key].pending }} pending</span>
          </span>
        </button>
      </div>

      <div class="card">
        <div v-if="error" class="alert alert-error">⚠️ {{ error }}</div>
        <div v-if="loading" class="loading-center"><div class="spinner"></div></div>
        <div v-else-if="!currentRows.length" class="empty-state">
          <div class="empty-state__icon">🛡️</div><div class="empty-state__title">Nothing in this range</div>
        </div>
        <div v-else class="table-wrap">
          <table class="tbl">
            <thead>
              <tr>
                <th>#</th><th>Posting Date</th><th>ID</th><th>{{ tab === 'sales_invoices' ? 'Customer' : 'Type' }}</th>
                <th>Security Passed</th><th>Scanned On</th><th>Scanned At</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in currentRows" :key="r.name">
                <td class="muted">{{ i + 1 }}</td>
                <td class="nowrap">{{ fmtDate(r.posting_date) }}</td>
                <td class="nowrap"><a :href="deskLink(r.name)" target="_blank" rel="noopener">{{ r.name }}</a></td>
                <td>{{ r.party }}</td>
                <td>
                  <span class="badge" :class="r.security_passed === 'Yes' ? 'badge-success' : 'badge-danger'">{{ r.security_passed || 'No' }}</span>
                </td>
                <td class="nowrap">{{ fmtDate(r.security_scanned_date) }}</td>
                <td>{{ r.security_scanned_from }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import AppHeader from '@/components/AppHeader.vue'
import DateRange from '@/components/DateRange.vue'
import { useAuthStore } from '@/stores/auth'
import { getSecurityScanReport } from '@/api/frappe'
import { fmtDate, toISODate, downloadCSV } from '@/utils/format'

const auth = useAuthStore()
const from = ref(toISODate())
const to = ref(toISODate())
const tab = ref('sales_invoices')
const tabs = [{ key: 'sales_invoices', label: 'Sales Invoices' }, { key: 'stock_entries', label: 'Stock Entries' }]
const data = ref({ sales_invoices: [], stock_entries: [] })
const summary = ref({})
const scanOptions = ref([])
const scannedFrom = ref('')
const status = ref('')
const loading = ref(false)
const error = ref('')

const currentRows = computed(() => (data.value[tab.value] || []).filter(r =>
  !status.value || (status.value === 'Yes' ? r.security_passed === 'Yes' : r.security_passed !== 'Yes')))

const deskLink = name => `/app/${tab.value === 'sales_invoices' ? 'sales-invoice' : 'stock-entry'}/${encodeURIComponent(name)}`

function onRange(r) { from.value = r.from; to.value = r.to; load() }

async function load() {
  if (!auth.boot) return
  loading.value = true
  error.value = ''
  try {
    const res = await getSecurityScanReport(from.value, to.value, scannedFrom.value || undefined)
    data.value = { sales_invoices: res.sales_invoices, stock_entries: res.stock_entries }
    summary.value = res.summary
    scanOptions.value = res.scanned_from_options || []
  } catch (err) {
    error.value = err.network ? 'Offline — reconnect to load the report' : err.message
  } finally {
    loading.value = false
  }
}

function exportCSV() {
  downloadCSV(`security-scan-${tab.value}-${from.value}-to-${to.value}.csv`, [
    { label: 'Posting Date', key: 'posting_date' }, { label: 'ID', key: 'name' },
    { label: tab.value === 'sales_invoices' ? 'Customer' : 'Type', key: 'party' },
    { label: 'Security Passed', key: 'security_passed' }, { label: 'Scanned On', key: 'security_scanned_date' },
    { label: 'Scanned At', key: 'security_scanned_from' },
  ], currentRows.value)
}

watch(() => auth.boot, () => load())
onMounted(load)
</script>

<style scoped>
.page-content--wide { max-width: 1100px; }
@media (min-width: 1024px) { .page-content--wide { max-width: 1100px; } }
.ss-filters { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }
.ss-filters .form-input { padding: 9px 12px; font-size: 14px; }
.tabs { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; }
.tab { background: white; border: 1.5px solid var(--slate-200); border-radius: var(--radius-lg); padding: 12px; text-align: left; font-family: inherit; font-weight: 700; font-size: 14px; color: var(--slate-700); display: flex; flex-direction: column; gap: 6px; }
.tab--on { border-color: var(--app-primary, #1e3a5f); box-shadow: 0 0 0 3px color-mix(in srgb, var(--app-primary, #1e3a5f) 15%, transparent); color: var(--app-primary, #1e3a5f); }
.tab__counts { display: flex; gap: 6px; flex-wrap: wrap; }
.table-wrap { overflow-x: auto; margin: 0 -16px; padding: 0 16px; }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--slate-500); padding: 8px 10px; border-bottom: 1.5px solid var(--slate-200); white-space: nowrap; }
.tbl td { padding: 10px; border-bottom: 1px solid var(--slate-100); }
.tbl a { color: var(--blue-600); text-decoration: none; font-weight: 600; }
.nowrap { white-space: nowrap; }
.muted { color: var(--slate-400); }
</style>
