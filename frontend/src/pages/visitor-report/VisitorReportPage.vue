<template>
  <div class="page">
    <AppHeader title="Visitor Report" :subtitle="auth.viewLocation ? `Gate ${auth.viewLocation}` : 'All gates'" active="visitor-report">
      <template #actions>
        <button class="icon-btn" :disabled="!rows.length" @click="exportCSV" title="Download CSV"><i class="pi pi-download"></i></button>
      </template>
    </AppHeader>

    <div class="page-content page-content--wide">
      <div class="card">
        <DateRange :from="from" :to="to" @change="onRange" />
      </div>

      <div class="stats">
        <div class="stat"><div class="stat__n">{{ summary.total ?? '–' }}</div><div class="stat__l">Visits</div></div>
        <div class="stat"><div class="stat__n">{{ summary.unique_visitors ?? '–' }}</div><div class="stat__l">Unique visitors</div></div>
        <div class="stat"><div class="stat__n">{{ summary.inside ?? '–' }}</div><div class="stat__l">Still inside</div></div>
        <div class="stat"><div class="stat__n">{{ summary.leads ?? '–' }}</div><div class="stat__l">CRM leads</div></div>
      </div>

      <div class="card">
        <div class="filters">
          <input v-model="q.text" class="form-input" placeholder="Search name, company, mobile…" />
          <select v-model="q.department" class="form-input">
            <option value="">All departments</option>
            <option v-for="d in (auth.boot?.departments || [])" :key="d">{{ d }}</option>
          </select>
          <select v-model="q.status" class="form-input">
            <option value="">Inside + exited</option>
            <option value="inside">Inside</option>
            <option value="out">Exited</option>
          </select>
        </div>

        <div v-if="error" class="alert alert-error">⚠️ {{ error }}</div>
        <div v-if="loading" class="loading-center"><div class="spinner"></div></div>
        <div v-else-if="!filtered.length" class="empty-state">
          <div class="empty-state__icon">📋</div><div class="empty-state__title">No visits in this range</div>
        </div>

        <div v-else class="table-wrap">
          <table class="tbl">
            <thead>
              <tr>
                <th>#</th>
                <th v-for="c in cols" :key="c.key" @click="sortBy(c.key)" class="sortable">
                  {{ c.label }}<span v-if="sort.key === c.key">{{ sort.dir > 0 ? ' ▲' : ' ▼' }}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in filtered" :key="r.name" @click="selected = r">
                <td class="muted">{{ i + 1 }}</td>
                <td class="nowrap">{{ fmtDateTime(r.date) }}</td>
                <td><strong>{{ r.name1 }}</strong></td>
                <td>{{ r.company_name }}</td>
                <td class="nowrap">{{ r.mobile_10 }}</td>
                <td>{{ r.location }}</td>
                <td>{{ r.department }}</td>
                <td>{{ r.city }}</td>
                <td>{{ r.territory }}</td>
                <td>{{ r.sales_person }}</td>
                <td class="nowrap">
                  <span v-if="r.docstatus === 0 && r.out !== 'Yes'" class="badge badge-warning">Inside</span>
                  <span v-else>{{ r.duration || '' }}</span>
                </td>
                <td class="nowrap">{{ r.crm_lead || '' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Detail sheet -->
    <div v-if="selected" class="modal" @click.self="selected = null">
      <div class="modal__card">
        <div class="det-head">
          <div><div class="det-name">{{ selected.name1 }}</div><div class="det-sub">{{ selected.name }}</div></div>
          <button class="det-close" @click="selected = null">✕</button>
        </div>
        <dl class="det">
          <template v-for="d in detailFields" :key="d.k">
            <template v-if="selected[d.k] || d.f">
              <dt>{{ d.l }}</dt><dd>{{ d.f ? d.f(selected) : selected[d.k] }}</dd>
            </template>
          </template>
        </dl>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import AppHeader from '@/components/AppHeader.vue'
import DateRange from '@/components/DateRange.vue'
import { useAuthStore } from '@/stores/auth'
import { getVisitorReport } from '@/api/frappe'
import { fmtDateTime, toISODate, downloadCSV, parseFrappeDate } from '@/utils/format'

const auth = useAuthStore()
const from = ref(toISODate())
const to = ref(toISODate())
const rows = ref([])
const summary = ref({})
const loading = ref(false)
const error = ref('')
const selected = ref(null)
const q = reactive({ text: '', department: '', status: '' })
const sort = reactive({ key: 'date', dir: -1 })

const cols = [
  { key: 'date', label: 'Date' }, { key: 'name1', label: 'Visitor' }, { key: 'company_name', label: 'Company' },
  { key: 'mobile_10', label: 'Mobile' }, { key: 'location', label: 'Gate' }, { key: 'department', label: 'Dept' },
  { key: 'city', label: 'City' }, { key: 'territory', label: 'Territory' }, { key: 'sales_person', label: 'Sales Person' },
  { key: 'duration', label: 'Duration' }, { key: 'crm_lead', label: 'CRM Lead' },
]
const detailFields = [
  { k: 'date', l: 'Check-in', f: r => fmtDateTime(r.date) },
  { k: 'out_date', l: 'Check-out', f: r => r.out_date ? fmtDateTime(r.out_date) : 'Inside' },
  { k: 'duration', l: 'Duration' }, { k: 'company_name', l: 'Company' }, { k: 'mobile_no', l: 'Mobile' },
  { k: 'location', l: 'Gate' }, { k: 'department', l: 'Department' }, { k: 'state', l: 'State' }, { k: 'city', l: 'City' },
  { k: 'territory', l: 'Territory' }, { k: 'sales_person', l: 'Sales Person' }, { k: 'customer', l: 'Customer' },
  { k: 'remarks', l: 'Remarks' }, { k: 'notes', l: 'Notes' }, { k: 'crm_lead', l: 'CRM Lead' },
]

const filtered = computed(() => {
  const t = q.text.trim().toLowerCase()
  let out = rows.value.filter(r => {
    if (q.department && r.department !== q.department) return false
    const inside = r.docstatus === 0 && r.out !== 'Yes'
    if (q.status === 'inside' && !inside) return false
    if (q.status === 'out' && inside) return false
    if (t && ![r.name1, r.company_name, r.mobile_no, r.city, r.crm_lead].some(x => (x || '').toLowerCase().includes(t))) return false
    return true
  })
  const { key, dir } = sort
  return [...out].sort((a, b) => {
    let x = a[key], y = b[key]
    if (key === 'date') { x = parseFrappeDate(x)?.getTime() || 0; y = parseFrappeDate(y)?.getTime() || 0 }
    if (x == null) return 1
    if (y == null) return -1
    return (typeof x === 'string' ? x.localeCompare(y) : x - y) * dir
  })
})

function sortBy(key) {
  if (sort.key === key) sort.dir = -sort.dir
  else { sort.key = key; sort.dir = key === 'date' ? -1 : 1 }
}

function onRange(r) { from.value = r.from; to.value = r.to; load() }

async function load() {
  if (!auth.boot) return
  loading.value = true
  error.value = ''
  try {
    const res = await getVisitorReport(from.value, to.value, auth.viewLocation || undefined)
    rows.value = res.rows
    summary.value = res.summary
  } catch (err) {
    error.value = err.network ? 'Offline — reconnect to load the report' : err.message
  } finally {
    loading.value = false
  }
}

function exportCSV() {
  downloadCSV(`visitor-report-${from.value}-to-${to.value}.csv`, [
    { label: 'ID', key: 'name' }, { label: 'Check-in', value: r => r.date }, { label: 'Check-out', value: r => r.out_date || '' },
    { label: 'Duration', key: 'duration' }, { label: 'Visitor', key: 'name1' }, { label: 'Company', key: 'company_name' },
    { label: 'Mobile', key: 'mobile_10' }, { label: 'Gate', key: 'location' }, { label: 'Department', key: 'department' },
    { label: 'State', key: 'state' }, { label: 'City', key: 'city' }, { label: 'Territory', key: 'territory' },
    { label: 'Sales Person', key: 'sales_person' }, { label: 'Customer', key: 'customer' }, { label: 'Remarks', key: 'remarks' },
    { label: 'Notes', key: 'notes' }, { label: 'CRM Lead', key: 'crm_lead' },
  ], filtered.value)
}

watch(() => [auth.boot, auth.viewLocation], () => load())
onMounted(load)
</script>

<style scoped>
.page-content--wide { max-width: 1200px; }
@media (min-width: 1024px) { .page-content--wide { max-width: 1200px; } }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 12px; }
@media (max-width: 560px) { .stats { grid-template-columns: repeat(2, 1fr); } }
.stat { background: white; border: 1px solid var(--slate-200); border-radius: var(--radius-lg); padding: 14px; box-shadow: var(--shadow-sm); }
.stat__n { font-size: 24px; font-weight: 800; color: var(--slate-900); font-variant-numeric: tabular-nums; }
.stat__l { font-size: 12px; color: var(--slate-500); margin-top: 2px; }
.filters { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 8px; margin-bottom: 12px; }
.filters .form-input { padding: 9px 12px; font-size: 14px; }
@media (max-width: 560px) { .filters { grid-template-columns: 1fr 1fr; } .filters input { grid-column: 1 / -1; } }
.table-wrap { overflow-x: auto; margin: 0 -16px; padding: 0 16px; }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--slate-500); padding: 8px 10px; border-bottom: 1.5px solid var(--slate-200); white-space: nowrap; background: white; position: sticky; top: 0; }
.tbl th.sortable { cursor: pointer; user-select: none; }
.tbl td { padding: 10px; border-bottom: 1px solid var(--slate-100); vertical-align: top; }
.tbl tbody tr { cursor: pointer; }
.tbl tbody tr:hover { background: var(--slate-50); }
.nowrap { white-space: nowrap; }
.muted { color: var(--slate-400); }
.modal { position: fixed; inset: 0; background: rgba(15,23,42,0.5); z-index: 500; display: flex; align-items: center; justify-content: center; padding: 16px; }
.modal__card { background: white; border-radius: 18px; padding: 22px; width: 100%; max-width: 520px; max-height: 90vh; overflow-y: auto; }
.det-head { display: flex; justify-content: space-between; margin-bottom: 14px; }
.det-name { font-size: 18px; font-weight: 800; }
.det-sub { font-size: 12px; color: var(--slate-500); }
.det-close { background: var(--slate-100); border: none; width: 32px; height: 32px; border-radius: 50%; }
.det { display: grid; grid-template-columns: 140px 1fr; gap: 8px 12px; font-size: 14px; }
.det dt { color: var(--slate-500); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; padding-top: 2px; }
.det dd { color: var(--slate-900); }
</style>
