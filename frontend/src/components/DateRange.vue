<template>
  <div class="dr">
    <div class="dr__chips">
      <button v-for="r in ranges" :key="r.id" class="dr__chip" :class="{ 'dr__chip--on': activeId === r.id }" @click="pick(r)">{{ r.label }}</button>
    </div>
    <div class="dr__inputs">
      <input type="date" class="form-input" :value="from" :max="to" @change="setFrom($event.target.value)" />
      <span class="dr__to">to</span>
      <input type="date" class="form-input" :value="to" :min="from" @change="setTo($event.target.value)" />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { toISODate } from '@/utils/format'

// Same presets as the Ionic ngx-daterangepicker.
const props = defineProps({ from: String, to: String })
const emit = defineEmits(['change'])

const d = (offset = 0) => { const x = new Date(); x.setDate(x.getDate() + offset); return x }
const monthStart = (m = 0) => { const x = new Date(); return new Date(x.getFullYear(), x.getMonth() + m, 1) }
const monthEnd = (m = 0) => { const x = new Date(); return new Date(x.getFullYear(), x.getMonth() + m + 1, 0) }

const ranges = [
  { id: 'today', label: 'Today',        f: () => d(),            t: () => d() },
  { id: 'yday',  label: 'Yesterday',    f: () => d(-1),          t: () => d(-1) },
  { id: '7',     label: 'Last 7 Days',  f: () => d(-6),          t: () => d() },
  { id: '30',    label: 'Last 30 Days', f: () => d(-29),         t: () => d() },
  { id: 'tm',    label: 'This Month',   f: () => monthStart(0),  t: () => monthEnd(0) },
  { id: 'lm',    label: 'Last Month',   f: () => monthStart(-1), t: () => monthEnd(-1) },
]
const activeId = ref('today')

function pick(r) {
  activeId.value = r.id
  emit('change', { from: toISODate(r.f()), to: toISODate(r.t()) })
}
function setFrom(v) { activeId.value = ''; emit('change', { from: v, to: props.to < v ? v : props.to }) }
function setTo(v)   { activeId.value = ''; emit('change', { from: props.from > v ? v : props.from, to: v }) }
</script>

<style scoped>
.dr__chips { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
.dr__chip { border: 1.5px solid var(--slate-200); background: white; border-radius: 20px; padding: 6px 12px; font-size: 12px; font-weight: 600; color: var(--slate-700); font-family: inherit; }
.dr__chip--on { background: var(--app-primary, #1e3a5f); border-color: var(--app-primary, #1e3a5f); color: white; }
.dr__inputs { display: flex; align-items: center; gap: 8px; }
.dr__inputs .form-input { padding: 8px 10px; font-size: 14px; }
.dr__to { font-size: 12px; color: var(--slate-500); }
</style>
