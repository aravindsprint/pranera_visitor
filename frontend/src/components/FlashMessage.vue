<template>
  <transition name="flash">
    <div v-if="flash.visible" class="flash" @click="hideFlash">
      <div class="flash__card">
        <div class="flash__icon" :class="`flash__icon--${flash.tone}`">{{ flash.icon }}</div>
        <div class="flash__title">{{ flash.title }}</div>
        <div v-if="flash.text" class="flash__text">{{ flash.text }}</div>
      </div>
    </div>
  </transition>
</template>

<script>
import { reactive } from 'vue'

// Full-screen 2-second confirmation — replaces the Ionic page's
// showFullScreenMessage() overlay ("Thanks for Coming!", "Welcome Back!").
export const flash = reactive({ visible: false, title: '', text: '', icon: '✓', tone: 'ok' })
let timer = null

export function showFlash(title, text = '', { icon = '✓', tone = 'ok', ms = 2000 } = {}) {
  Object.assign(flash, { visible: true, title, text, icon, tone })
  clearTimeout(timer)
  timer = setTimeout(hideFlash, ms)
}
export function hideFlash() { flash.visible = false }

export default { setup: () => ({ flash, hideFlash }) }
</script>

<style scoped>
.flash { position: fixed; inset: 0; background: rgba(15,23,42,0.55); z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 24px; }
.flash__card { background: white; border-radius: 20px; padding: 32px 28px; text-align: center; max-width: 360px; width: 100%; box-shadow: var(--shadow-lg); }
.flash__icon { width: 72px; height: 72px; border-radius: 50%; margin: 0 auto 16px; display: flex; align-items: center; justify-content: center; font-size: 36px; }
.flash__icon--ok   { background: var(--emerald-100); color: var(--emerald-700); }
.flash__icon--info { background: var(--blue-100); color: var(--blue-600); }
.flash__icon--warn { background: var(--amber-100); color: var(--amber-600); }
.flash__title { font-size: 20px; font-weight: 800; color: var(--slate-900); }
.flash__text  { font-size: 15px; color: var(--slate-500); margin-top: 8px; line-height: 1.45; white-space: pre-line; }
.flash-enter-active, .flash-leave-active { transition: opacity 0.2s; }
.flash-enter-from, .flash-leave-to { opacity: 0; }
</style>
