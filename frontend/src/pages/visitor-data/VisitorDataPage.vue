<template>
  <div class="page">
    <AppHeader title="Visitor Data" :subtitle="subtitle" active="visitor-data">
      <template #actions>
        <button class="icon-btn" :disabled="loadingList" @click="loadActive" title="Refresh">
          <i class="pi pi-refresh" :class="{ 'pi-spin': loadingList }"></i>
        </button>
      </template>
    </AppHeader>

    <div class="page-content">
      <div v-if="auth.error" class="alert alert-error">⚠️ {{ auth.error }}</div>

      <!-- Admin without a gate picked -->
      <div v-if="auth.canViewAll && !auth.location" class="card gate-pick">
        <div class="section-title">Which gate are you at?</div>
        <div class="gate-pick__row">
          <button v-for="l in locations" :key="l" class="btn btn-outline btn-lg" @click="auth.setAdminLocation(l)">{{ l }}</button>
        </div>
      </div>

      <!-- ── Step 1: mobile + department ─────────────────────────────────── -->
      <div v-else-if="step === 'mobile'" class="card checkin">
        <div class="checkin__head">
          <div class="checkin__welcome">Welcome</div>
          <div class="checkin__gate">Gate {{ auth.location }}</div>
        </div>
        <form @submit.prevent="submitMobile" novalidate>
          <div class="form-group">
            <label class="form-label">Mobile No</label>
            <input ref="mobileInput" v-model="form.mobile_no" class="form-input form-input--xl" type="tel"
              inputmode="numeric" maxlength="10" placeholder="10-digit mobile" autocomplete="off"
              @input="form.mobile_no = form.mobile_no.replace(/\D/g, '').slice(0, 10)" />
            <div v-if="tried && mobileError" class="field-error">{{ mobileError }}</div>
          </div>
          <DepartmentPicker v-model="form.department" :options="departments" />
          <div v-if="tried && !form.department" class="field-error">Department is required.</div>
          <button type="submit" class="btn btn-primary btn-full btn-lg" :disabled="busy" style="margin-top:16px">
            <span v-if="busy" class="btn-spinner"></span>{{ busy ? 'Checking…' : 'Continue' }}
          </button>
        </form>
      </div>

      <!-- ── Step 2: visitor details ─────────────────────────────────────── -->
      <div v-else class="card checkin">
        <div class="checkin__head">
          <div>
            <div class="checkin__welcome">{{ known ? 'Welcome back' : 'New visitor' }}</div>
            <div class="checkin__sub" v-if="known && lastVisit">Last visit {{ fmtDateTime(lastVisit) }}</div>
          </div>
          <div class="checkin__gate">Gate {{ auth.location }}</div>
        </div>
        <form @submit.prevent="submitDetails" novalidate>
          <div class="grid-2">
            <div class="form-group">
              <label class="form-label">Mobile No</label>
              <input v-model="form.mobile_no" class="form-input" type="tel" inputmode="numeric" maxlength="10"
                @input="form.mobile_no = form.mobile_no.replace(/\D/g, '').slice(0, 10)" />
              <div v-if="tried && mobileError" class="field-error">{{ mobileError }}</div>
            </div>
            <div class="form-group">
              <label class="form-label">Name</label>
              <input v-model="form.name" class="form-input" type="text" placeholder="Visitor name" autocomplete="off" />
              <div v-if="tried && form.name.trim().length < 3" class="field-error">Name should be at least 3 characters.</div>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">Company Name</label>
            <input v-model="form.company_name" class="form-input" type="text" placeholder="Company" autocomplete="off" />
            <div v-if="tried && form.company_name.trim().length < 3" class="field-error">Company Name should be at least 3 characters.</div>
          </div>
          <DepartmentPicker v-model="form.department" :options="departments" />
          <div v-if="tried && !form.department" class="field-error">Department is required.</div>
          <div class="grid-2" style="margin-top:16px">
            <div class="form-group">
              <label class="form-label">State</label>
              <AutoComplete v-model="form.state" :options="stateOptions" placeholder="Search state" allow-custom @change="onStateChange" />
            </div>
            <div class="form-group">
              <label class="form-label">City</label>
              <AutoComplete v-model="form.city" :options="cityOptions" placeholder="Search or type city" allow-custom />
              <div v-if="tried && !form.city" class="field-error">City is required.</div>
            </div>
          </div>
          <div class="form-actions">
            <button type="button" class="btn btn-ghost" @click="resetForm">Back</button>
            <button type="submit" class="btn btn-primary btn-lg" :disabled="busy" style="flex:1">
              <span v-if="busy" class="btn-spinner"></span>{{ busy ? 'Saving…' : 'Check In' }}
            </button>
          </div>
        </form>
      </div>

      <!-- ── Active visitors ─────────────────────────────────────────────── -->
      <div class="card">
        <div class="list-head">
          <div class="section-title" style="border:none;margin:0;padding:0">
            Inside now <span class="badge badge-info">{{ active.length }}</span>
          </div>
          <input v-model="search" class="form-input list-search" placeholder="Search name / mobile / company" />
        </div>

        <div v-if="loadingList && !active.length" class="loading-center"><div class="spinner"></div></div>
        <div v-else-if="!filteredActive.length" class="empty-state">
          <div class="empty-state__icon">🚪</div>
          <div class="empty-state__title">{{ search ? 'No match' : 'No visitors inside' }}</div>
        </div>

        <div v-else class="vlist">
          <div v-for="(v, i) in filteredActive" :key="v.name || v.client_id" class="vrow"
               :class="{ 'vrow--long': isLong(v), 'vrow--pending': v._pending }">
            <div class="vrow__idx">{{ i + 1 }}</div>
            <div class="vrow__main">
              <div class="vrow__name">{{ v.name1 }}</div>
              <div class="vrow__meta">
                {{ v.company_name }} · {{ v.mobile_10 || v.mobile_no }}
                <span v-if="auth.canViewAll && !auth.viewLocation"> · {{ v.location }}</span>
              </div>
              <div class="vrow__tags">
                <span class="dept" :class="`dept--${(v.department || '').toLowerCase()}`">{{ v.department || '—' }}</span>
                <span class="vrow__time">In {{ fmtTime(v.date) }} · {{ hms(v.date, now) }}</span>
                <span v-if="v._pending" class="badge badge-warning">Not synced</span>
                <span v-else-if="v.crm_lead" class="badge badge-success" title="CRM Lead">{{ v.crm_lead }}</span>
              </div>
            </div>
            <div class="vrow__actions">
              <button class="act act--edit" :disabled="v._pending || !isOnline" @click="openEdit(v)" title="Edit details">
                <i class="pi pi-pencil"></i>
              </button>
              <button class="act act--exit" @click="askExit(v)" title="Mark as exited">
                <i class="pi pi-sign-out"></i><span>Exit</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Exit confirm -->
    <div v-if="exitTarget" class="modal" @click.self="exitTarget = null">
      <div class="modal__card modal__card--sm">
        <div class="modal__title">Confirm Exit</div>
        <div class="exit-name">{{ exitTarget.name1 }}</div>
        <div class="exit-meta">{{ exitTarget.company_name }} · inside {{ hms(exitTarget.date, now) }}</div>
        <div class="form-actions">
          <button class="btn btn-ghost" style="flex:1" @click="exitTarget = null">No</button>
          <button class="btn btn-danger" style="flex:1" :disabled="busy" @click="confirmExit">Yes, Exit</button>
        </div>
      </div>
    </div>

    <!-- Message dialog (already inside, errors) -->
    <div v-if="dialog" class="modal" @click.self="dialog = null">
      <div class="modal__card modal__card--sm">
        <div class="modal__title">{{ dialog.title }}</div>
        <div class="dialog-text">{{ dialog.text }}</div>
        <button class="btn btn-primary btn-full" @click="dialog = null">OK</button>
      </div>
    </div>

    <EditVisitorModal v-if="editTarget" :visitor="editTarget" @close="editTarget = null" @saved="onEdited" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import AppHeader from '@/components/AppHeader.vue'
import AutoComplete from '@/components/AutoComplete.vue'
import DepartmentPicker from '@/components/DepartmentPicker.vue'
import EditVisitorModal from './EditVisitorModal.vue'
import { showFlash } from '@/components/FlashMessage.vue'
import { useAuthStore } from '@/stores/auth'
import { isOnline, enqueue, newClientId, flushQueue } from '@/composables/useSync'
import { db, cacheGet, cacheSet } from '@/db'
import { lookupMobile, checkIn, markExit, getActiveVisitors } from '@/api/frappe'
import { INDIA_STATES, INDIA_CITIES } from '@/data/indiaLocations'
import { fmtDateTime, fmtTime, hms, minutesSince, normaliseMobile, toFrappeDatetime } from '@/utils/format'

const auth = useAuthStore()

const locations   = computed(() => auth.boot?.locations || ['HO', 'JV'])
const departments = computed(() => auth.boot?.departments || ['Fabric', 'Garments', 'Others'])
const longStayMin = computed(() => auth.boot?.long_stay_minutes || 60)
const subtitle    = computed(() => auth.viewLocation ? `Gate ${auth.viewLocation}` : (auth.canViewAll ? 'All gates' : ''))

// ── Form ──────────────────────────────────────────────────────────────────
const step  = ref('mobile')            // 'mobile' | 'details'
const known = ref(false)
const lastVisit = ref('')
const tried = ref(false)
const busy  = ref(false)
const mobileInput = ref(null)
const blank = () => ({ mobile_no: '', department: '', name: '', company_name: '', state: '', city: '' })
const form  = reactive(blank())

const mobileError = computed(() => {
  if (!form.mobile_no) return 'Mobile No is required.'
  if (!/^[0-9]{10}$/.test(form.mobile_no)) return 'Enter a valid 10-digit mobile number.'
  return ''
})

// States are stored by label (e.g. "Tamil Nadu"), cities keyed by state code.
const stateOptions = INDIA_STATES.map(s => ({ label: s.label, value: s.label }))
const stateCode = computed(() => INDIA_STATES.find(s => s.label.toLowerCase() === (form.state || '').toLowerCase())?.value)
const cityOptions = computed(() => (INDIA_CITIES[stateCode.value] || []).map(c => c.label))
function onStateChange() { form.city = '' }

function resetForm() {
  Object.assign(form, blank())
  step.value = 'mobile'
  known.value = false
  lastVisit.value = ''
  tried.value = false
  nextTick(() => mobileInput.value?.focus())
}

const dialog = ref(null)
function showDialog(title, text) { dialog.value = { title, text } }

function insideLocally(ten) {
  return active.value.find(v => normaliseMobile(v.mobile_no) === ten)
}

async function submitMobile() {
  tried.value = true
  if (mobileError.value || !form.department) return
  const ten = form.mobile_no
  const already = insideLocally(ten)
  if (already) {
    showDialog('Already Checked In', `${already.name1} (${ten}) is already inside. Mark them as exited before checking in again.`)
    return
  }
  busy.value = true
  try {
    const res = await lookupMobile(ten)
    if (res.status === 'inside') {
      showDialog('Already Checked In', `${res.visitor.name1} (${ten}) is already inside at ${res.visitor.location}. Mark them as exited before checking in again.`)
      loadActive()
      return
    }
    if (res.status === 'returning_today') {
      // Same day re-entry: check straight in with the details from earlier today.
      const l = res.last
      await doCheckIn({
        mobile_no: ten, department: form.department, name: l.name1, company_name: l.company_name,
        state: l.state || '', city: l.city || '',
      }, { welcomeBack: l.date })
      return
    }
    tried.value = false
    step.value = 'details'
    if (res.status === 'known') {
      const l = res.last
      known.value = true
      lastVisit.value = l.date
      form.name = l.name1 || ''
      form.company_name = l.company_name || ''
      form.state = l.state || ''
      form.city = l.city || ''
      showFlash(`Welcome Back! ${l.name1 || ''}`, `You last visited us on\n${fmtDateTime(l.date)}`, { icon: '👋', tone: 'info' })
    }
  } catch (err) {
    if (err.network) {
      // Offline: same as the Ionic app — open a blank form, save locally.
      tried.value = false
      step.value = 'details'
    } else {
      showDialog('Error', err.message)
    }
  } finally {
    busy.value = false
  }
}

async function submitDetails() {
  tried.value = true
  if (mobileError.value || form.name.trim().length < 3 || form.company_name.trim().length < 3 || !form.department || !form.city) return
  if (insideLocally(form.mobile_no)) {
    showDialog('Already Checked In', `This visitor (${form.mobile_no}) is already inside.`)
    return
  }
  await doCheckIn({ ...form, name: form.name.trim(), company_name: form.company_name.trim() })
}

async function doCheckIn(payload, { welcomeBack } = {}) {
  busy.value = true
  const client_id = newClientId()
  const data = { ...payload, location: auth.location, checked_in_at: toFrappeDatetime() }
  try {
    const res = await checkIn(data, client_id)
    if (res.status === 'inside') {
      showDialog('Already Checked In', `${res.visitor.name1} is already inside.`)
    } else if (welcomeBack) {
      showFlash(`Welcome Back! ${payload.name}`, `You already visited us today at ${fmtTime(welcomeBack)}`, { icon: '👋', tone: 'info' })
    } else {
      showFlash('Thanks for Coming!', payload.name, { icon: '🤝' })
    }
    resetForm()
    loadActive()
  } catch (err) {
    if (err.network) {
      await enqueue('check_in', data, client_id)
      active.value = [{
        _pending: true, client_id, name1: data.name, company_name: data.company_name,
        mobile_no: data.mobile_no, mobile_10: data.mobile_no, department: data.department,
        location: data.location, date: data.checked_in_at,
      }, ...active.value]
      persistActive()
      showFlash('Saved on this device', `${payload.name}\nIt will sync when the network is back.`, { icon: '📥', tone: 'warn', ms: 2500 })
      resetForm()
    } else {
      showDialog('Could not check in', err.message)
    }
  } finally {
    busy.value = false
  }
}

// ── Active list ───────────────────────────────────────────────────────────
const active = ref([])
const loadingList = ref(false)
const search = ref('')
const now = ref(Date.now())

const filteredActive = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return active.value
  return active.value.filter(v =>
    [v.name1, v.company_name, v.mobile_no, v.department].some(x => (x || '').toLowerCase().includes(q)))
})
const isLong = v => minutesSince(v.date, now.value) > longStayMin.value

const cacheKey = () => `active:${auth.frappeUser}:${auth.viewLocation || 'all'}`
function persistActive() { cacheSet(cacheKey(), JSON.parse(JSON.stringify(active.value))) }

async function pendingRows() {
  const items = await db.queue.where('status').equals('pending').toArray()
  const exits = new Set(items.filter(i => i.type === 'exit').map(i => i.payload.name || i.payload.check_in_client_id))
  const rows = items.filter(i => i.type === 'check_in' && !exits.has(i.client_id)).map(i => ({
    _pending: true, client_id: i.client_id, name1: i.payload.name, company_name: i.payload.company_name,
    mobile_no: i.payload.mobile_no, mobile_10: i.payload.mobile_no, department: i.payload.department,
    location: i.payload.location, date: i.payload.checked_in_at,
  }))
  return { rows, exits }
}

async function loadActive() {
  if (!auth.boot) return
  loadingList.value = true
  try {
    const server = await getActiveVisitors(auth.viewLocation || undefined)
    const { rows, exits } = await pendingRows()
    active.value = [...rows, ...server.filter(v => !exits.has(v.name))]
    persistActive()
  } catch (err) {
    if (err.network) {
      const cached = await cacheGet(cacheKey())
      if (cached) active.value = cached
    } else {
      showDialog('Could not load visitors', err.message)
    }
  } finally {
    loadingList.value = false
  }
}

// ── Exit ──────────────────────────────────────────────────────────────────
const exitTarget = ref(null)
function askExit(v) { exitTarget.value = v }

async function confirmExit() {
  const v = exitTarget.value
  busy.value = true
  const drop = () => {
    active.value = active.value.filter(x => (x.name || x.client_id) !== (v.name || v.client_id))
    persistActive()
  }
  try {
    if (v._pending) {
      // Not synced yet — queue the exit behind its check-in.
      const item = await db.queue.where('client_id').equals(v.client_id).first()
      await enqueue('exit', { check_in_client_id: v.client_id, check_in_payload: item?.payload })
      drop()
      flushQueue()
    } else {
      await markExit(v.name)
      drop()
    }
    showFlash('Thanks for Visiting — Come Again!', v.name1, { icon: '👋' })
  } catch (err) {
    if (err.network) {
      await enqueue('exit', { name: v.name, mobile_no: v.mobile_no })
      drop()
      showFlash('Exit saved on this device', `${v.name1}\nIt will sync when the network is back.`, { icon: '📥', tone: 'warn', ms: 2500 })
    } else {
      showDialog('Could not mark exit', err.message)
    }
  } finally {
    busy.value = false
    exitTarget.value = null
  }
}

// ── Edit ──────────────────────────────────────────────────────────────────
const editTarget = ref(null)
function openEdit(v) { editTarget.value = v }
function onEdited(updated) {
  const i = active.value.findIndex(x => x.name === updated.name)
  if (i !== -1) active.value[i] = { ...active.value[i], ...updated }
  persistActive()
}

// ── Lifecycle ─────────────────────────────────────────────────────────────
let tick = null, refresh = null
const onSynced = () => loadActive()

watch(() => [auth.boot, auth.viewLocation], () => loadActive())

onMounted(() => {
  loadActive()
  tick = setInterval(() => { now.value = Date.now() }, 1000)
  refresh = setInterval(() => { if (isOnline.value) loadActive() }, 60_000)
  window.addEventListener('visitor:queue-synced', onSynced)
  nextTick(() => mobileInput.value?.focus())
})
onUnmounted(() => {
  clearInterval(tick); clearInterval(refresh)
  window.removeEventListener('visitor:queue-synced', onSynced)
})
</script>

<style scoped>
.checkin__head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; gap: 12px; }
.checkin__welcome { font-size: 20px; font-weight: 800; color: var(--slate-900); }
.checkin__sub { font-size: 12px; color: var(--slate-500); margin-top: 2px; }
.checkin__gate { background: var(--slate-100); color: var(--slate-700); font-weight: 700; font-size: 12px; padding: 4px 10px; border-radius: 20px; white-space: nowrap; }
.form-input--xl { font-size: 22px; letter-spacing: 0.08em; padding: 14px; text-align: center; font-weight: 600; }
.field-error { color: var(--red-600); font-size: 12px; margin-top: 4px; }
.form-actions { display: flex; gap: 10px; margin-top: 8px; }
.gate-pick__row { display: flex; gap: 12px; }
.gate-pick__row .btn { flex: 1; }

.list-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.list-search { max-width: 280px; padding: 8px 12px; font-size: 14px; }
@media (max-width: 480px) { .list-search { max-width: none; } }

.vlist { display: flex; flex-direction: column; }
.vrow { display: flex; align-items: center; gap: 12px; padding: 12px 4px; border-top: 1px solid var(--slate-100); }
.vrow:first-child { border-top: none; }
.vrow--long { background: #fff7ed; border-radius: 10px; }
.vrow--long .vrow__time { color: var(--red-600); font-weight: 700; }
.vrow--pending { opacity: 0.85; }
.vrow__idx { width: 24px; text-align: center; font-size: 12px; color: var(--slate-400); font-weight: 700; }
.vrow__main { flex: 1; min-width: 0; }
.vrow__name { font-weight: 700; font-size: 15px; color: var(--slate-900); }
.vrow__meta { font-size: 12px; color: var(--slate-500); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.vrow__tags { display: flex; gap: 6px; align-items: center; margin-top: 6px; flex-wrap: wrap; }
.vrow__time { font-size: 12px; color: var(--slate-500); font-variant-numeric: tabular-nums; }
.vrow__actions { display: flex; gap: 6px; }
.act { border: none; border-radius: 10px; height: 40px; min-width: 40px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; font-weight: 700; font-size: 13px; padding: 0 12px; font-family: inherit; }
.act:disabled { opacity: 0.4; }
.act--edit { background: var(--slate-100); color: var(--slate-700); }
.act--exit { background: var(--red-600); color: white; }

.dept { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 12px; background: var(--slate-100); color: var(--slate-700); }
.dept--fabric   { background: var(--blue-100); color: var(--blue-600); }
.dept--garments { background: #f3e8ff; color: #7e22ce; }
.dept--others   { background: var(--amber-100); color: var(--amber-600); }

.modal { position: fixed; inset: 0; background: rgba(15,23,42,0.5); z-index: 500; display: flex; align-items: center; justify-content: center; padding: 16px; }
.modal__card { background: white; border-radius: 18px; padding: 22px; width: 100%; max-width: 560px; max-height: 92vh; overflow-y: auto; box-shadow: var(--shadow-lg); }
.modal__card--sm { max-width: 380px; text-align: center; }
.modal__title { font-size: 17px; font-weight: 800; margin-bottom: 14px; }
.exit-name { font-size: 22px; font-weight: 800; color: var(--slate-900); }
.exit-meta { font-size: 13px; color: var(--slate-500); margin: 6px 0 18px; }
.dialog-text { font-size: 14px; color: var(--slate-700); margin-bottom: 18px; line-height: 1.5; }

.btn-spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid rgba(255,255,255,0.4); border-top-color: #fff; border-radius: 50%; animation: spin 0.7s linear infinite; margin-right: 6px; vertical-align: -2px; }
</style>
