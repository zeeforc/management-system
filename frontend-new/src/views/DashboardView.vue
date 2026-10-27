<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import AppLayout from '@/components/AppLayout.vue'

interface DashboardSummary {
  wib_reference_date: string
  total_products: number
  total_active_variants: number
  total_customers: number
  active_rentals: number
  rentals_expiring_in_5_days: number
  rentals_expiring_in_3_days: number
  rentals_expiring_tomorrow: number
  expired_rentals: number
  pending_renewal_requests: number
  pending_payment_verifications: number
  verified_payment_totals: string
  currency: string
  failed_notifications: number
}

interface Rental {
  id: string
  customer_name: string
  product_name: string
  variant_name: string
  expiration_date: string
  effective_status: string
  days_remaining: number
}

const auth = useAuthStore()
const summary = ref<DashboardSummary | null>(null)
const rentals = ref<Rental[]>([])
const loading = ref(true)
const error = ref('')
const activeChart = ref<'rentals' | 'finance'>('rentals')

const today = new Intl.DateTimeFormat('id-ID', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  timeZone: 'Asia/Jakarta',
}).format(new Date())

const upcomingRentals = computed(() => rentals.value)

const ringCircumference = 2 * Math.PI * 40
const ringProgress = computed(() => {
  if (!summary.value) return 0
  const productCount = summary.value.total_products
  const customerCount = summary.value.total_customers
  const total = productCount + customerCount
  return total === 0 ? 0 : (productCount / total) * ringCircumference
})

const selectedMetrics = computed(() => {
  if (!summary.value) return []
  if (activeChart.value === 'rentals') {
    return [
      { label: 'Rental aktif', value: summary.value.active_rentals },
      { label: 'Habis tepat H+5', value: summary.value.rentals_expiring_in_5_days },
      { label: 'Sudah berakhir', value: summary.value.expired_rentals },
    ]
  }
  return [
    { label: 'Menunggu verifikasi', value: summary.value.pending_payment_verifications },
    { label: 'Renewal menunggu', value: summary.value.pending_renewal_requests },
    { label: 'Notifikasi gagal', value: summary.value.failed_notifications },
  ]
})

function formatMoney(value: string, currency: string) {
  const amount = Number(value)
  return `${currency} ${Number.isFinite(amount) ? amount.toLocaleString('id-ID') : value}`
}

function formatShortDate(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString('id-ID', { day: 'numeric', month: 'short' })
}

function statusLabel(status: string) {
  if (status === 'SCHEDULED') return 'Terjadwal'
  if (status === 'ACTIVE') return 'Aktif'
  if (status === 'EXPIRING_SOON') return 'Segera habis'
  if (status === 'EXPIRED') return 'Kedaluwarsa'
  if (status === 'CANCELLED') return 'Dibatalkan'
  return status.replaceAll('_', ' ').toLowerCase()
}

async function fetchDashboard() {
  loading.value = true
  error.value = ''
  try {
    const response = await api.get('/dashboard/overview')
    summary.value = response.data.summary
    rentals.value = response.data.upcoming_rentals
  } catch (e: any) {
    error.value = e.response?.data?.detail ?? 'Gagal memuat dashboard. Coba muat ulang halaman.'
  } finally {
    loading.value = false
  }
}

onMounted(fetchDashboard)
</script>

<template>
  <AppLayout>
  <div class="animate-fade-up space-y-6">
    <header class="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        <p class="mb-1 text-xs font-bold uppercase tracking-[0.2em] text-[#1c1c1f]/35">{{ today }}</p>
        <h1 class="text-3xl font-extrabold tracking-tight text-[#1c1c1f] sm:text-[34px]">
          Halo, {{ auth.user?.full_name?.split(' ')[0] || 'Admin' }}!
        </h1>
        <p class="mt-1 text-sm text-[#1c1c1f]/45">Ini ringkasan bisnis rental kamu hari ini.</p>
      </div>
      <RouterLink
        :to="{ name: 'rentals' }"
        class="inline-flex items-center justify-center gap-2 self-start rounded-full bg-[#1c1c1f] px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-black/10 transition duration-200 hover:-translate-y-0.5 hover:bg-[#303035] sm:self-auto"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14m7-7H5" />
        </svg>
        Buat rental
      </RouterLink>
    </header>

    <div v-if="loading" class="grid gap-4 lg:grid-cols-3">
      <div v-for="item in 3" :key="item" class="h-64 animate-pulse rounded-[30px] bg-white/50" />
    </div>
    <div v-else-if="error" class="bento-white flex items-center justify-between gap-4 p-5 text-sm text-rose-700">
      <span>{{ error }}</span>
      <button class="shrink-0 rounded-full bg-[#1c1c1f] px-4 py-2 text-xs font-semibold text-white" @click="fetchDashboard">Coba lagi</button>
    </div>

    <template v-else-if="summary">
      <section class="grid gap-4 xl:grid-cols-12">
        <article class="bento-dark animate-fade-up p-6 sm:p-7 xl:col-span-4">
          <div class="flex items-start justify-between">
            <div>
              <p class="text-sm font-semibold text-white/55">Ringkasan rental</p>
              <p class="mt-5 text-5xl font-extrabold tracking-tight">{{ summary.active_rentals }}</p>
              <p class="mt-1 text-xs text-white/45">rental aktif saat ini</p>
            </div>
            <button
              class="rounded-full bg-white/10 p-2.5 text-white/70 transition hover:rotate-12 hover:bg-white/20 hover:text-white"
              aria-label="Buka daftar rental"
              @click="$router.push({ name: 'rentals' })"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M7 17 17 7M7 7h10v10" />
              </svg>
            </button>
          </div>
          <div class="mt-7 grid grid-cols-3 gap-2">
            <div v-for="(metric, index) in [
              { label: 'Customer', value: summary.total_customers },
              { label: 'Produk', value: summary.total_products },
              { label: 'Varian', value: summary.total_active_variants },
            ]" :key="metric.label" class="animate-fade-up rounded-[20px] bg-white/[0.09] p-3 text-center" :class="`delay-${(index + 1) * 75}`">
              <p class="text-2xl font-bold">{{ metric.value }}</p>
              <p class="mt-0.5 text-[10px] font-semibold uppercase tracking-wider text-white/45">{{ metric.label }}</p>
            </div>
          </div>
        </article>

        <article class="bento-glass animate-fade-up p-6 sm:p-7 xl:col-span-5 delay-75">
          <div class="flex items-start justify-between gap-3">
            <div>
              <h2 class="text-lg font-bold tracking-tight text-[#1c1c1f]">Aktivitas rental</h2>
              <p class="mt-1 text-xs text-[#1c1c1f]/40">Status masa sewa saat ini</p>
            </div>
            <div class="flex rounded-full bg-[#1c1c1f]/[0.06] p-1">
              <button
                v-for="tab in [{ id: 'rentals', label: 'Rental' }, { id: 'finance', label: 'Perlu aksi' }]"
                :key="tab.id"
                class="rounded-full px-3 py-1.5 text-[11px] font-bold transition-all"
                :class="activeChart === tab.id ? 'bg-[#1c1c1f] text-white shadow-sm' : 'text-[#1c1c1f]/45 hover:text-[#1c1c1f]'"
                @click="activeChart = tab.id as 'rentals' | 'finance'"
              >
                {{ tab.label }}
              </button>
            </div>
          </div>

          <div class="mt-7 space-y-5">
            <div v-for="(metric, index) in selectedMetrics" :key="metric.label" class="animate-fade-up" :class="`delay-${(index + 1) * 75}`">
              <div class="mb-2 flex items-center justify-between text-xs">
                <span class="font-semibold text-[#1c1c1f]/60">{{ metric.label }}</span>
                <span class="font-bold text-[#1c1c1f]">{{ metric.value }}</span>
              </div>
              <div class="h-2 overflow-hidden rounded-full bg-[#1c1c1f]/[0.07]">
                <div
                  class="h-full rounded-full bg-[#1c1c1f] transition-all duration-700 ease-out"
                  :style="{ width: `${Math.min(100, metric.value === 0 ? 0 : (metric.value / Math.max(1, ...selectedMetrics.map((entry) => entry.value))) * 100)}%`, opacity: 1 - index * 0.22 }"
                />
              </div>
            </div>
          </div>
          <RouterLink :to="{ name: activeChart === 'rentals' ? 'rentals' : 'dashboard' }" class="mt-6 inline-flex items-center gap-1 text-xs font-bold text-[#1c1c1f]/55 transition hover:text-[#1c1c1f]">
            {{ activeChart === 'rentals' ? 'Lihat semua rental' : 'Periksa aktivitas' }}
            <span aria-hidden="true">↗</span>
          </RouterLink>
        </article>

        <article class="bento-white animate-fade-up p-6 sm:p-7 xl:col-span-3 delay-150">
          <div class="flex items-start justify-between">
            <div>
              <h2 class="text-lg font-bold tracking-tight">Katalog</h2>
              <p class="mt-1 text-xs text-[#1c1c1f]/40">Produk dan pelanggan</p>
            </div>
            <svg class="h-5 w-5 text-[#1c1c1f]/35" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M3 3v18h18M7 14l4-4 4 4 6-7" />
            </svg>
          </div>
          <div class="mt-3 flex items-center justify-center">
            <div class="relative flex h-36 w-36 items-center justify-center">
              <svg class="h-36 w-36 -rotate-90" viewBox="0 0 100 100" aria-label="Perbandingan produk dan customer">
                <circle cx="50" cy="50" r="40" fill="none" stroke="#ececef" stroke-width="8" />
                <circle cx="50" cy="50" r="40" fill="none" stroke="#1c1c1f" stroke-width="8" stroke-linecap="round" :stroke-dasharray="`${ringProgress} ${ringCircumference}`" class="transition-all duration-1000" />
                <circle cx="50" cy="50" r="30" fill="none" stroke="#bdbdc2" stroke-width="2.5" />
                <circle cx="50" cy="50" r="24" fill="none" stroke="#d9d9dd" stroke-width="2" />
              </svg>
              <div class="absolute text-center">
                <p class="text-2xl font-extrabold tracking-tight">{{ summary.total_products + summary.total_customers }}</p>
                <p class="text-[9px] font-bold uppercase tracking-widest text-[#1c1c1f]/40">Data</p>
              </div>
            </div>
          </div>
          <div class="mt-2 space-y-2">
            <div class="flex items-center justify-between text-xs">
              <span class="flex items-center gap-2 text-[#1c1c1f]/55"><i class="h-2 w-2 rounded-full bg-[#1c1c1f]" /> Produk</span>
              <span class="font-bold">{{ summary.total_products }}</span>
            </div>
            <div class="flex items-center justify-between text-xs">
              <span class="flex items-center gap-2 text-[#1c1c1f]/55"><i class="h-2 w-2 rounded-full bg-[#bdbdc2]" /> Customer</span>
              <span class="font-bold">{{ summary.total_customers }}</span>
            </div>
          </div>
        </article>
      </section>

      <section class="grid gap-4 xl:grid-cols-12">
        <article class="bento-white animate-fade-up p-6 sm:p-7 xl:col-span-4 delay-75">
          <div class="flex items-center justify-between">
            <div>
              <h2 class="text-lg font-bold tracking-tight">Perlu diperhatikan</h2>
              <p class="mt-1 text-xs text-[#1c1c1f]/40">Antrian yang butuh tindak lanjut</p>
            </div>
            <span class="rounded-full bg-[#1c1c1f]/[0.06] px-3 py-1 text-xs font-bold">{{ summary.pending_payment_verifications + summary.pending_renewal_requests }}</span>
          </div>
          <div class="mt-5 space-y-3">
            <RouterLink :to="{ name: 'rentals' }" class="flex items-center justify-between rounded-[20px] bg-[#f3f3f5] p-4 transition hover:bg-[#e9e9ec]">
              <div class="flex items-center gap-3">
                <span class="flex h-9 w-9 items-center justify-center rounded-2xl bg-white">
                  <svg class="h-4 w-4 text-[#1c1c1f]/65" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3Z" />
                  </svg>
                </span>
                <span class="text-xs font-semibold">Verifikasi pembayaran</span>
              </div>
              <span class="text-sm font-extrabold">{{ summary.pending_payment_verifications }}</span>
            </RouterLink>
            <div class="flex items-center justify-between rounded-[20px] bg-[#f3f3f5] p-4">
              <div class="flex items-center gap-3">
                <span class="flex h-9 w-9 items-center justify-center rounded-2xl bg-white">
                  <svg class="h-4 w-4 text-[#1c1c1f]/65" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M4 4v5h5M20 20v-5h-5M5 9a7 7 0 0112-3l3 3M19 15a7 7 0 01-12 3l-3-3" />
                  </svg>
                </span>
                <span class="text-xs font-semibold">Permintaan renewal</span>
              </div>
              <span class="text-sm font-extrabold">{{ summary.pending_renewal_requests }}</span>
            </div>
          </div>
        </article>

        <article class="bento-glass animate-fade-up p-6 sm:p-7 xl:col-span-8 delay-150">
          <div class="flex items-start justify-between gap-4">
            <div>
              <h2 class="text-lg font-bold tracking-tight">Masa aktif terdekat</h2>
              <p class="mt-1 text-xs text-[#1c1c1f]/40">Rental yang paling dekat dengan tanggal berakhir</p>
            </div>
            <RouterLink :to="{ name: 'rentals' }" class="shrink-0 rounded-full border border-[#1c1c1f]/10 px-3.5 py-2 text-xs font-bold text-[#1c1c1f]/60 transition hover:bg-[#1c1c1f] hover:text-white">
              Semua rental
            </RouterLink>
          </div>

          <div v-if="upcomingRentals.length" class="mt-5 grid gap-3 md:grid-cols-3">
            <div v-for="(rental, index) in upcomingRentals" :key="rental.id" class="task-card-tilted rounded-[24px] bg-white p-4 shadow-sm" :class="index === 1 ? 'md:rotate-0' : ''">
              <div class="flex items-start justify-between gap-2">
                <span class="flex h-9 w-9 items-center justify-center rounded-2xl bg-[#f0f0f2] text-[#1c1c1f]/65">
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0Z" />
                  </svg>
                </span>
                <span class="rounded-full bg-[#f0f0f2] px-2.5 py-1 text-[10px] font-bold">{{ statusLabel(rental.effective_status) }}</span>
              </div>
              <p class="mt-4 truncate text-sm font-bold">{{ rental.customer_name }}</p>
              <p class="mt-1 truncate text-xs text-[#1c1c1f]/45">
                {{ rental.product_name }} · {{ rental.variant_name }}
              </p>
              <div class="mt-4 flex items-end justify-between border-t border-[#1c1c1f]/[0.06] pt-3">
                <span class="text-[10px] font-medium text-[#1c1c1f]/40">Berakhir {{ formatShortDate(rental.expiration_date) }}</span>
                <span class="text-xs font-extrabold">{{ rental.days_remaining }} hari</span>
              </div>
            </div>
          </div>
          <div v-else class="mt-6 rounded-[22px] bg-white/60 p-6 text-center text-sm text-[#1c1c1f]/45">
            Belum ada rental aktif atau terjadwal.
          </div>
        </article>
      </section>

      <section class="grid gap-4 md:grid-cols-3">
        <RouterLink :to="{ name: 'rentals' }" class="bento-dark group animate-fade-up p-5 delay-75">
          <div class="flex items-center justify-between">
            <span class="text-sm font-bold">Kelola rental</span>
            <span class="transition-transform group-hover:translate-x-1">↗</span>
          </div>
          <p class="mt-2 text-xs text-white/45">Buat rental baru dan pantau tanggal berakhir.</p>
        </RouterLink>
        <RouterLink :to="{ name: 'customers' }" class="bento-white group animate-fade-up p-5 delay-150">
          <div class="flex items-center justify-between">
            <span class="text-sm font-bold">Data customer</span>
            <span class="transition-transform group-hover:translate-x-1">↗</span>
          </div>
          <p class="mt-2 text-xs text-[#1c1c1f]/45">Kelola profil dan riwayat pelanggan.</p>
        </RouterLink>
        <RouterLink :to="{ name: 'products' }" class="bento-white group animate-fade-up p-5 delay-225">
          <div class="flex items-center justify-between">
            <span class="text-sm font-bold">Katalog produk</span>
            <span class="transition-transform group-hover:translate-x-1">↗</span>
          </div>
          <p class="mt-2 text-xs text-[#1c1c1f]/45">Atur produk dan varian harga rental.</p>
        </RouterLink>
      </section>

      <footer class="flex flex-col justify-between gap-1 px-1 pb-2 text-[11px] text-[#1c1c1f]/35 sm:flex-row">
        <span>Tanggal referensi WIB: {{ summary.wib_reference_date }}</span>
        <span>Pendapatan terverifikasi: {{ formatMoney(summary.verified_payment_totals, summary.currency) }}</span>
      </footer>
    </template>
  </div>
  </AppLayout>
</template>
