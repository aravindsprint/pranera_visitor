<template>
  <div>
    <label class="form-label">Department</label>
    <div class="dp">
      <button v-for="d in options" :key="d" type="button" class="dp__opt"
        :class="{ 'dp__opt--on': modelValue === d }" @click="$emit('update:modelValue', d)">
        <span class="dp__icon">{{ icons[d] || '•' }}</span>{{ d }}
      </button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: String, default: '' },
  options: { type: Array, default: () => ['Fabric', 'Garments', 'Others'] },
})
defineEmits(['update:modelValue'])
const icons = { Fabric: '🧵', Garments: '👕', Others: '📦' }
</script>

<style scoped>
.dp { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.dp__opt { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 12px 6px; border-radius: var(--radius-md); border: 1.5px solid var(--slate-200); background: white; font-size: 14px; font-weight: 600; color: var(--slate-700); font-family: inherit; transition: all 0.15s; }
.dp__opt--on { border-color: var(--app-primary, #1e3a5f); background: color-mix(in srgb, var(--app-primary, #1e3a5f) 8%, white); color: var(--app-primary, #1e3a5f); box-shadow: 0 0 0 3px color-mix(in srgb, var(--app-primary, #1e3a5f) 15%, transparent); }
.dp__icon { font-size: 22px; }
</style>
