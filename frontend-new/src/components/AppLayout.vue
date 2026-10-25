<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const mobileMenuOpen = ref(false)

function logout() {
  auth.logout()
  router.push({ name: 'login' })
}

const navItems = [
  { name: 'dashboard', label: 'Dashboard', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
  { name: 'rentals', label: 'Rental', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2' },
  { name: 'renewals', label: 'Renewal', icon: 'M4 4v6h6M20 20v-6h-6M5.6 15a7 7 0 0011.55 2.6L20 14M4 10l2.85-3.6A7 7 0 0118.4 9' },
  { name: 'notifications', label: 'Notifikasi', icon: 'M18 8a6 6 0 00-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4' },
  { name: 'customers', label: 'Customer', icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z' },
  { name: 'products', label: 'Produk', icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4' },
]
</script>

<template>
  <div class="min-h-screen p-3 sm:p-4 lg:p-5">
    <!-- Outer glass shell -->
    <div class="glass-shell rounded-[32px] min-h-[calc(100vh-24px)] sm:min-h-[calc(100vh-32px)] lg:min-h-[calc(100vh-40px)] flex flex-col lg:flex-row overflow-hidden">

      <!-- Sidebar (dark bento) — desktop -->
      <aside class="hidden lg:flex w-[220px] shrink-0 flex-col bg-white/85 rounded-[28px] m-3 p-5 text-[#1c1c1f] shadow-sm shadow-black/[0.03]">
        <!-- Logo -->
        <RouterLink :to="{ name: 'dashboard' }" class="flex items-center gap-3 mb-8">
          <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[#1c1c1f]">
            <svg class="h-5 w-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5v-9Z M4.5 7.8 12 12l7.5-4.2M12 12v8.5" />
            </svg>
          </span>
          <span class="text-sm font-bold tracking-tight">Rental Mgmt</span>
        </RouterLink>

        <!-- Nav items -->
        <nav class="flex flex-col gap-1.5 flex-1">
          <RouterLink
            v-for="item in navItems"
            :key="item.name"
            :to="{ name: item.name }"
            class="flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition-all duration-200"
            :class="route.name === item.name
              ? 'bg-[#1c1c1f] text-white shadow-lg shadow-black/10'
              : 'text-[#1c1c1f]/55 hover:text-[#1c1c1f] hover:bg-[#1c1c1f]/[0.05]'"
          >
            <svg class="h-[18px] w-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" :d="item.icon" />
            </svg>
            {{ item.label }}
          </RouterLink>
        </nav>

        <!-- User section -->
        <div class="mt-auto pt-5 border-t border-[#1c1c1f]/[0.08]">
          <div class="flex items-center gap-3 mb-3">
            <div class="h-9 w-9 rounded-full bg-[#1c1c1f]/[0.06] flex items-center justify-center text-xs font-bold text-[#1c1c1f]/75">
              {{ auth.user?.full_name?.charAt(0)?.toUpperCase() || 'U' }}
            </div>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-semibold truncate text-[#1c1c1f]/90">{{ auth.user?.full_name }}</p>
              <p class="text-[11px] text-[#1c1c1f]/40">Administrator</p>
            </div>
          </div>
          <button
            @click="logout"
            class="w-full flex items-center justify-center gap-2 rounded-2xl border border-[#1c1c1f]/10 px-3 py-2.5 text-xs font-semibold text-[#1c1c1f]/50 transition hover:bg-[#1c1c1f] hover:text-white"
          >
            <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Keluar
          </button>
        </div>
      </aside>

      <!-- Mobile header -->
      <header class="lg:hidden flex items-center justify-between px-5 py-4">
        <RouterLink :to="{ name: 'dashboard' }" class="flex items-center gap-2.5">
          <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#1c1c1f] text-white">
            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5v-9Z M4.5 7.8 12 12l7.5-4.2M12 12v8.5" />
            </svg>
          </span>
          <span class="text-sm font-bold tracking-tight text-[#1c1c1f]">Rental Mgmt</span>
        </RouterLink>
        <div class="flex items-center gap-2">
          <span class="hidden sm:block text-sm font-medium text-[#1c1c1f]/60 truncate max-w-32">{{ auth.user?.full_name }}</span>
          <button
            @click="mobileMenuOpen = !mobileMenuOpen"
            class="h-10 w-10 rounded-2xl bg-[#1c1c1f]/5 flex items-center justify-center text-[#1c1c1f]/70 transition hover:bg-[#1c1c1f]/10"
          >
            <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path v-if="!mobileMenuOpen" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M4 6h16M4 12h16M4 18h16" />
              <path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </header>

      <!-- Mobile nav dropdown -->
      <nav v-if="mobileMenuOpen" class="lg:hidden mx-4 mb-3 rounded-2xl bg-white/95 p-3 shadow-lg ring-1 ring-[#1c1c1f]/[0.06] animate-pop-in">
        <RouterLink
          v-for="item in navItems"
          :key="item.name"
          :to="{ name: item.name }"
          @click="mobileMenuOpen = false"
          class="flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold transition-all duration-200"
          :class="route.name === item.name
            ? 'bg-[#1c1c1f] text-white'
            : 'text-[#1c1c1f]/55 hover:bg-[#1c1c1f]/[0.05] hover:text-[#1c1c1f]'"
        >
          <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" :d="item.icon" />
          </svg>
          {{ item.label }}
        </RouterLink>
        <button
          @click="logout"
          class="w-full mt-2 flex items-center justify-center gap-2 rounded-xl border border-[#1c1c1f]/10 py-2.5 text-xs font-semibold text-[#1c1c1f]/50 transition hover:bg-[#1c1c1f] hover:text-white"
        >
          Keluar
        </button>
      </nav>

      <!-- Main content -->
      <main class="flex-1 overflow-y-auto px-4 py-4 sm:px-6 sm:py-5 lg:px-8 lg:py-6">
        <slot />
      </main>
    </div>
  </div>
</template>
