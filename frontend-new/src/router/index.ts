import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/dashboard',
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { requiresGuest: true },
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/products',
      name: 'products',
      component: () => import('@/views/ProductsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/customers',
      name: 'customers',
      component: () => import('@/views/CustomersView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/rentals',
      name: 'rentals',
      component: () => import('@/views/RentalsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/renewals',
      name: 'renewals',
      component: () => import('@/views/RenewalsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/notifications',
      name: 'notifications',
      component: () => import('@/views/NotificationsView.vue'),
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login' }
  }

  if (to.meta.requiresGuest && auth.isAuthenticated) {
    return { name: 'dashboard' }
  }
})

export default router
