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
      <div class="em-cust" :class="`em-cust--${cust.status || 'loading'}`">
        <template v-if="custLoading"><span class="spinner spinner--sm"></span> Looking up customer…</template>
        <template v-else-if="cust.status === 'found'">
          ✅ Customer <strong>{{ cust.customer_name }}</strong>
          <span v-if="cust.matched_by === 'company_name'"> (matched by company name — a contact will be linked on save)</span>
          <div v-if="cust.sales_person" class="em-cust__sp">Sales person: {{ cust.sales_person }}</div>
        </template>
        <template v-else-if="cust.status === 'contact_only'">
          👤 Contact <strong>{{ cust.full_name }}</strong> exists but isn't linked to a customer.
          <button class="btn btn-outline em-cust__btn" :disabled="creating" @click="doCreateCustomer">{{ creating ? 'Creating…' : 'Create Customer' }}</button>
        </template>
        <template v-else>
          ➕ Not an existing customer.
          <button class="btn btn-outline em-cust__btn" :disabled="creating" @click="doCreateCustomer">{{ creating ? 'Creating…' : 'Create Customer' }}</button>
        </template>
      </div>

      <div class="grid-2">
        <div class="form-group">
          <label class="form-label">Sales Person</label>
          <AutoComplete v-model="f.sales_person" :options="boot.sales_persons || []" placeholder="Select" />
        </div>
        <div class="form-group">
          <label class="form-label">Customer Type</label>
          <select v-model="f.customer_type" class="form-input"><option value=""></option><option v-for="o in opt.customer_types" :key="o">{{ o }}</option></select>
        </div>
        <div class="form-group">
          <label class="form-label">ERPNext Customer Type</label>
          <select v-model="f.erpnext_customer_type" class="form-input"><option value=""></option><option v-for="o in opt.erpnext_customer_types" :key="o">{{ o }}</option></select>
        </div>
        <div class="form-group">
          <label class="form-label">Customer Group</label>
          <AutoComplete v-model="f.customer_group" :options="boot.customer_groups || []" placeholder="Select" />
        </div>
        <div class="form-group">
          <label class="form-label">Source</label>
          <select v-model="f.source" class="form-input"><option value=""></option><option v-for="o in opt.sources" :key="o">{{ o }}</option></select>
        </div>
        <div class="form-group">
          <label class="form-label">Territory</label>
          <AutoComplete v-model="f.territory" :options="boot.territories || []" placeholder="Select" />
        </div>
        <div class="form-group">
          <label class="form-label">Commercial Name</label>
          <AutoComplete v-model="f.commercial_name" :options="opt.commercial_names || []" placeholder="Select or type" allow-custom />
        </div>
        <div class="form-group">
          <label class="form-label">Color</label>
          <AutoComplete v-model="f.color" :options="opt.colors || []" placeholder="Select or type" allow-custom />
        </div>
        <div class="form-group">
          <label class="form-label">Sample Qty</label>
          <input v-model="f.sample_qty" class="form-input" type="number" inputmode="decimal" min="0" />
        </div>
        <div class="form-group">
          <label class="form-label">Bulk Qty</label>
          <input v-model="f.bulk_qty" class="form-input" type="number" inputmode="decimal" min="0" />
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

const FIELDS = ['sales_person', 'customer_type', 'erpnext_customer_type', 'customer_group', 'source',
  'territory', 'commercial_name', 'color', 'sample_qty', 'bulk_qty', 'remarks', 'notes']
const f = reactive(Object.fromEntries(FIELDS.map(k => [k, props.visitor[k] ?? ''])))

const cust = ref({})
const custLoading = ref(true)
const creating = ref(false)
const saving = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    cust.value = await lookupCustomer(props.visitor.name)
    // Prefill from the matched customer when the visitor row is still empty.
    if (cust.value.status === 'found') {
      if (!f.customer_group && cust.value.customer_group) f.customer_group = cust.value.customer_group
      if (!f.territory && cust.value.territory) f.territory = cust.value.territory
      if (!f.sales_person && cust.value.sales_person) f.sales_person = cust.value.sales_person
      if (!f.customer_type) f.customer_type = 'Existing'
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
      territory: f.territory, customer_group: f.customer_group, sales_person: f.sales_person,
      erpnext_customer_type: f.erpnext_customer_type || 'Company',
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
.em-actions { display: flex; gap: 10px; margin-top: 4px; }
.spinner--sm { width: 14px; height: 14px; border-width: 2px; display: inline-block; vertical-align: -2px; margin-right: 6px; }
</style>
