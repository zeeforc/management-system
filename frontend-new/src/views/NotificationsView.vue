<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import api from '@/lib/api'
import AppLayout from '@/components/AppLayout.vue'

interface NotificationAttempt {
  id: string
  attempt_number: number
  started_at: string
  finished_at: string | null
  result_status: string
  telegram_message_id: number | null
  error_code: string | null
  error_summary: string | null
}

interface Notification {
  id: string
  rental_id: string
  customer_id: string
  reminder_stage: string
  expiration_version: number
  scheduled_at: string
  status: string
  attempt_count: number
  sent_at: string | null
  telegram_message_id: number | null
  last_error: string | null
  customer_display_name: string | null
  customer_telegram_username: string | null
  product_name: string | null
  product_variant_name: string | null
  expiration_date: string | null
  attempts: NotificationAttempt[]
}

const notifications = ref<Notification[]>([])
const loading = ref(true)
const error = ref('')
const activeFilter = ref<'all' | 'attention'>('all')

const visibleNotifications = computed(() =>
  notifications.value.filter((notification) =>
    activeFilter.value === 'all'
      ? true
      : ['FAILED_RETRYABLE', 'FAILED_PERMANENT', 'AMBIGUOUS'].includes(notification.status),
  ),
)

function statusStyle(status: string) {
  if (status === 'SENT') return 'bg-emerald-50 text-emerald-700'
  if (status === 'FAILED_PERMANENT' || status === 'AMBIGUOUS') return 'bg-rose-50 text-rose-700'
  if (status === 'FAILED_RETRYABLE') return 'bg-amber-50 text-amber-700'
  if (status === 'CANCELLED') return 'bg-slate-100 text-slate-500'
  return 'bg-slate-100 text-slate-700'
}

function formatDate(value: string | null) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('id-ID', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Jakarta',
  }).format(new Date(value))
}

function customerLabel(notification: Notification) {
  if (!notification.customer_display_name) return 'Customer tidak ditemukan'
  return notification.customer_telegram_username
    ? `${notification.customer_display_name} · @${notification.customer_telegram_username}`
    : notification.customer_display_name
}

function rentalLabel(notification: Notification) {
  const productLabel = notification.product_name
    ? `${notification.product_name}${notification.product_variant_name ? ` / ${notification.product_variant_name}` : ''}`
    : 'Produk'
  return `${productLabel} · berakhir ${formatDate(notification.expiration_date)}`
}

async function fetchNotifications() {
  loading.value = true
  error.value = ''
  try {
    const notificationResponse = await api.get('/notifications?page=1&page_size=100')
    notifications.value = notificationResponse.data.items
  } catch {
    error.value = 'Log notifikasi gagal dimuat. Coba muat ulang.'
  } finally {
    loading.value = false
  }
}

onMounted(fetchNotifications)
</script>

<template>
  <AppLayout>
    <div class="animate-fade-up space-y-5">
      <header class="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p class="mb-1 text-[11px] font-bold uppercase tracking-[0.2em] text-[#1c1c1f]/35">
            Otomatisasi & delivery
          </p>
          <h1 class="bento-page-title">Notifikasi</h1>
          <p class="mt-1 text-sm text-[#1c1c1f]/45">
            Riwayat H-5, H-3, H-1 dan hasil pengiriman Telegram.
          </p>
        </div>
        <button
          class="bento-primary w-full px-5 py-3 text-sm font-semibold sm:w-auto"
          :disabled="loading"
          @click="fetchNotifications"
        >
          {{ loading ? 'Memuat...' : 'Muat ulang' }}
        </button>
      </header>

      <div class="grid gap-3 sm:grid-cols-2">
        <button
          class="bento-glass p-4 text-left transition hover:-translate-y-0.5"
          :class="activeFilter === 'all' ? 'ring-1 ring-[#1c1c1f]/20' : ''"
          @click="activeFilter = 'all'"
        >
          <span class="text-xs font-semibold uppercase tracking-wider text-[#1c1c1f]/40">Semua log</span>
          <span class="mt-1 block text-2xl font-bold text-[#1c1c1f]">{{ notifications.length }}</span>
        </button>
        <button
          class="bento-glass p-4 text-left transition hover:-translate-y-0.5"
          :class="activeFilter === 'attention' ? 'ring-1 ring-rose-300' : ''"
          @click="activeFilter = 'attention'"
        >
          <span class="text-xs font-semibold uppercase tracking-wider text-rose-700/60">Perlu perhatian</span>
          <span class="mt-1 block text-2xl font-bold text-rose-700">
            {{ notifications.filter((item) => ['FAILED_RETRYABLE', 'FAILED_PERMANENT', 'AMBIGUOUS'].includes(item.status)).length }}
          </span>
        </button>
      </div>

      <div v-if="error" class="bento-white border border-rose-200 p-4 text-sm text-rose-700">
        {{ error }}
        <button class="ml-2 font-semibold underline" @click="fetchNotifications">Coba lagi</button>
      </div>
      <div v-else-if="loading" class="grid gap-3">
        <div v-for="item in 4" :key="item" class="h-28 animate-pulse rounded-[28px] bg-white/50" />
      </div>
      <div v-else-if="visibleNotifications.length === 0" class="bento-glass py-16 text-center">
        <p class="font-semibold text-[#1c1c1f]/70">Belum ada catatan notifikasi</p>
        <p class="mt-1 text-sm text-[#1c1c1f]/40">Reminder yang sudah dijadwalkan akan muncul di sini.</p>
      </div>

      <div v-else class="space-y-3">
        <article
          v-for="notification in visibleNotifications"
          :key="notification.id"
          class="bento-white animate-fade-up p-4 sm:p-5"
        >
          <div class="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-full bg-[#1c1c1f]/[0.06] px-2.5 py-1 text-xs font-bold text-[#1c1c1f]/70">
                  {{ notification.reminder_stage }}
                </span>
                <span class="rounded-full px-2.5 py-1 text-xs font-semibold" :class="statusStyle(notification.status)">
                  {{ notification.status.replaceAll('_', ' ') }}
                </span>
                <span class="text-xs text-[#1c1c1f]/35">Versi {{ notification.expiration_version }}</span>
              </div>
              <p class="mt-3 truncate text-sm font-semibold text-[#1c1c1f]">
                {{ customerLabel(notification) }}
              </p>
              <p class="mt-1 text-xs text-[#1c1c1f]/45">
                {{ rentalLabel(notification) }}
              </p>
              <p class="mt-1 text-xs text-[#1c1c1f]/45">Jadwal reminder: {{ formatDate(notification.scheduled_at) }}</p>
            </div>
            <div class="shrink-0 text-left sm:text-right">
              <p class="text-xs text-[#1c1c1f]/40">Attempts</p>
              <p class="text-lg font-bold text-[#1c1c1f]">{{ notification.attempt_count }}</p>
              <p v-if="notification.sent_at" class="text-xs text-emerald-700">
                Terkirim {{ formatDate(notification.sent_at) }}
              </p>
            </div>
          </div>

          <div
            v-if="notification.last_error || notification.attempts.length"
            class="mt-4 rounded-2xl bg-[#1c1c1f]/[0.035] p-3"
          >
            <p v-if="notification.last_error" class="break-words text-xs leading-5 text-rose-700">
              {{ notification.last_error }}
            </p>
            <div v-if="notification.attempts.length" class="mt-2 space-y-2">
              <div
                v-for="attempt in notification.attempts"
                :key="attempt.id"
                class="flex flex-col gap-1 border-t border-[#1c1c1f]/[0.06] pt-2 text-xs sm:flex-row sm:justify-between"
              >
                <span class="font-semibold text-[#1c1c1f]/65">
                  Attempt {{ attempt.attempt_number }} · {{ attempt.result_status.replaceAll('_', ' ') }}
                </span>
                <span class="text-[#1c1c1f]/40">{{ formatDate(attempt.started_at) }}</span>
                <span v-if="attempt.error_summary" class="break-words text-rose-700 sm:max-w-[50%]">
                  {{ attempt.error_summary }}
                </span>
              </div>
            </div>
          </div>
        </article>
      </div>
    </div>
  </AppLayout>
</template>
