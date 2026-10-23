import { createRouter, createWebHistory } from 'vue-router'
import { isLoggedIn } from '@/api/frappe'

// All eager — the gate must keep working when the network drops.
import LoginPage          from '@/pages/login/LoginPage.vue'
import VisitorDataPage    from '@/pages/visitor-data/VisitorDataPage.vue'
import VisitorReportPage  from '@/pages/visitor-report/VisitorReportPage.vue'
import SecurityScanPage   from '@/pages/security-scan/SecurityScanPage.vue'

export const HOME = '/visitor-app/visitor-data'

const routes = [
  { path: '/',            redirect: HOME },
  { path: '/visitor-app', redirect: HOME },
  { path: '/visitor-app/login',          component: LoginPage },
  { path: '/visitor-app/visitor-data',   component: VisitorDataPage },
  { path: '/visitor-app/visitor-report', component: VisitorReportPage },
  { path: '/visitor-app/security-scan',  component: SecurityScanPage },
  { path: '/visitor-app/:pathMatch(.*)*', redirect: HOME },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  const loggedIn = isLoggedIn()
  if (to.path !== '/visitor-app/login' && !loggedIn) {
    return { path: '/visitor-app/login', query: { redirect: to.fullPath } }
  }
  if (to.path === '/visitor-app/login' && loggedIn) return { path: HOME }
  return true
})

export default router
