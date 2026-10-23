<template>
  <div class="modal" @click.self="$emit('close')">
    <div class="modal__card">
      <div class="em-head">
        <div>
          <div class="modal__title" style="margin:0">{{ visitor.name1 }}</div>
          <div class="em-sub">{{ visitor.company_name }} · {{ visitor.mobile_10 || visitor.mobile_no }} · {{ visitor.name }}</div>
        </div>
        <button class="em-close" @click="$emit('close')">✕</button>
      </div>

      <!-- Customer lookup (port of lookupCustomer / createCustomer) -->
      <div class="em-cust" :class="`em-cust--${custLoading ? 'loading' : (cust.status || 'not_found')}`">
        <template v-if="custLoading"><span class="spinner spinner--sm"></span> Looking up customer…</template>
        <template v-else-if="cust.status === 'found'">
          ✅ Customer <strong>{{ cust.customer_name }}</strong>
          <span v-if="cust.matched_by === 'company_name'"> (matched by company name — a contact will be linked on save)</span>
          <div v-if="cust.sales_person" class="em-cust__sp">Sales person: {{ cust.sales_person }}</div>
        </template>
        <template v-else>
          <div v-if="cust.status === 'contact_only'">👤 Contact <strong>{{ cust.full_name }}</strong> exists but isn't linked to a customer.</div>
          <div v-else>➕ Not an existing customer.</div>
          <div class="em-newcust">
            <select v-model="newCust.erpnext_customer_type" class="form-input" title="Customer type">
              <option v-for="o in opt.erpnext_customer_types" :key="o">{{ o }}</option>
            </select>
            <AutoComplete v-model="newCust.customer_group" :options="boot.customer_groups || []" placeholder="Group" />
            <button class="btn btn-outline" :disabled="creating" @click="doCreateCustomer">{{ creating ? 'Creating…' : 'Create Customer' }}</button>
          </div>
        </template>
      </div>

      <div class="grid-2">
        <div class="form-group">
          <label class="form-label">Sales Person</label>
          <AutoComplete v-model="f.sales_person" :options="boot.sales_persons || []" placeholder="Select" />
        </div>
        <div class="form-group">
          <label class="form-label">Territory</label>
          <AutoComplete v-model="f.territory" :options="boot.territories || []" placeholder="Select" />
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">Remarks</label>
        <AutoComplete v-model="f.remarks" :options="opt.remarks || []" placeholder="Select or type" allow-custom />
      </div>
      <div class="form-group">
        <label class="form-label">Notes</label>
        <textarea v-model="f.notes" class="form-input" rows="3"></textarea>
      </div>

      <div v-if="error" class="alert alert-error">⚠️ {{ error }}</div>
      <div class="em-actions">
        <button class="btn btn-ghost" @click="$emit('close')">Cancel</button>
        <button class="btn btn-primary" style="flex:1" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save' }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import AutoComplete from '@/components/AutoComplete.vue'
import { showFlash } from '@/components/FlashMessage.vue'
import { useAuthStore } from '@/stores/auth'
import { lookupCustomer, createCustomer, updateVisitor } from '@/api/frappe'

const props = defineProps({ visitor: { type: Object, required: true } })
const emit = defineEmits(['close', 'saved'])

const auth = useAuthStore()
const boot = computed(() => auth.boot || {})
const opt  = computed(() => boot.value.options || {})

const FIELDS = ['sales_person', 'territory', 'remarks', 'notes']
const f = reactive(Object.fromEntries(FIELDS.map(k => [k, props.visitor[k] ?? ''])))

const cust = ref({})
// Used only if a new Customer is created from here — not stored on the visit.
const newCust = reactive({ erpnext_customer_type: 'Company', customer_group: '' })
const custLoading = ref(true)
const creating = ref(false)
const saving = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    cust.value = await lookupCustomer(props.visitor.name)
    // Prefill from the matched customer when the visitor row is still empty.
    if (cust.value.status === 'found') {
      if (!f.territory && cust.value.territory) f.territory = cust.value.territory
      if (!f.sales_person && cust.value.sales_person) f.sales_person = cust.value.sales_person
    }
  } catch (err) {
    cust.value = { status: 'not_found' }
  } finally {
    custLoading.value = false
  }
})

async function doCreateCustomer() {
  creating.value = true
  error.value = ''
  try {
    const r = await createCustomer(props.visitor.name, {
      territory: f.territory, sales_person: f.sales_person,
      customer_group: newCust.customer_group || undefined,
      erpnext_customer_type: newCust.erpnext_customer_type || 'Company',
    })
    cust.value = { status: 'found', matched_by: 'mobile', customer_name: r.customer_name, customer_id: r.customer_id }
    showFlash(r.customer_reused ? 'Contact linked to existing customer' : 'Customer Created!', r.customer_name)
  } catch (err) {
    error.value = err.message
  } finally {
    creating.value = false
  }
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    const linkContact = cust.value.status === 'found' && cust.value.matched_by === 'company_name'
    const res = await updateVisitor(props.visitor.name, { ...f }, linkContact)
    emit('saved', res.visitor)
    showFlash('Visitor updated!', res.contact_linked_to ? `${props.visitor.name1}\nContact linked to ${res.contact_linked_to}` : props.visitor.name1)
    emit('close')
  } catch (err) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.modal { position: fixed; inset: 0; background: rgba(15,23,42,0.5); z-index: 500; display: flex; align-items: center; justify-content: center; padding: 16px; }
.modal__card { background: white; border-radius: 18px; padding: 22px; width: 100%; max-width: 620px; max-height: 92vh; overflow-y: auto; box-shadow: var(--shadow-lg); }
.modal__title { font-size: 18px; font-weight: 800; }
.em-head { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.em-sub { font-size: 12px; color: var(--slate-500); margin-top: 2px; }
.em-close { background: var(--slate-100); border: none; width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0; }
.em-cust { border-radius: 12px; padding: 12px 14px; font-size: 13px; margin-bottom: 16px; background: var(--slate-50); border: 1px solid var(--slate-200); line-height: 1.5; }
.em-cust--found { background: var(--emerald-100); border-color: transparent; color: var(--emerald-700); }
.em-cust--contact_only { background: var(--blue-100); border-color: transparent; color: var(--blue-600); }
.em-cust__sp { font-size: 12px; margin-top: 2px; }
.em-cust__btn { padding: 6px 12px; font-size: 12px; margin-left: 8px; }
.em-newcust { display: grid; grid-template-columns: 130px 1fr auto; gap: 8px; margin-top: 10px; }
.em-newcust .form-input { padding: 8px 10px; font-size: 13px; }
.em-newcust .btn { padding: 8px 12px; font-size: 13px; background: white; }
@media (max-width: 480px) { .em-newcust { grid-template-columns: 1fr 1fr; } .em-newcust .btn { grid-column: 1 / -1; } }
.em-actions { display: flex; gap: 10px; margin-top: 4px; }
.spinner--sm { width: 14px; height: 14px; border-width: 2px; display: inline-block; vertical-align: -2px; margin-right: 6px; }
</style>
