<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppLayout from '@/components/AppLayout.vue'
import api from '@/lib/api'

interface Rental {
  id: string
  customer_id: string
  start_date: string
  expiration_date: string
  agreed_price: string
  currency: string
  status: string
}

interface Customer {
  id: string
  display_name: string
}

interface Renewal {
  id: string
  rental_id: string
  previous_expiration_date: string
  new_start_date: string
  new_expiration_date: string
  duration_value: number
  duration_unit: string
  renewal_model: string
  agreed_price: string
  currency: string
  status: string
  created_at: string
}

interface Payment {
  id: string
  customer_id: string
  rental_id: string
  renewal_id: string | null
  amount: string
  currency: string
  payment_method: string
  status: string
  payment_reference: string | null
  verified_at: string | null
}

const renewals = ref<Renewal[]>([])
const rentals = ref<Rental[]>([])
const customers = ref<Customer[]>([])
const payments = ref<Payment[]>([])
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const notice = ref('')

const showOfferModal = ref(false)
const showApprovalModal = ref(false)
const showPaymentModal = ref(false)
const selectedRenewal = ref<Renewal | null>(null)

const offerForm = ref({
  rental_id: '',
  offered_duration_value: 1,
  offered_duration_unit: 'MONTHS',
  offered_price: '',
  currency: 'IDR',
  renewal_model: 'CONTINUOUS',
  expires_in_hours: 72,
})
const approvalForm = ref({ renewal_model: 'CONTINUOUS', confirmed_start_date: '' })
const paymentForm = ref({
  amount: '',
  payment_method: 'BANK_TRANSFER',
  payment_reference: '',
})

const pendingCount = computed(() => renewals.value.filter((item) => item.status === 'PENDING').length)
const approvedCount = computed(() => renewals.value.filter((item) => item.status === 'APPROVED').length)

function rentalFor(id: string) {
  return rentals.value.find((rental) => rental.id === id)
}

function customerName(customerId: string) {
  return customers.value.find((customer) => customer.id === customerId)?.display_name
    ?? `Customer ${customerId.slice(0, 8)}`
}

function amountInMinorUnits(amount: string) {
  const [whole, fraction = ''] = amount.split('.')
  return BigInt(whole || '0') * 100n + BigInt(fraction.padEnd(2, '0').slice(0, 2))
}

function verifiedAmount(renewalId: string) {
  const cents = payments.value
    .filter((payment) => payment.renewal_id === renewalId && payment.status === 'PAID' && payment.verified_at)
    .reduce((total, payment) => total + amountInMinorUnits(payment.amount), 0n)
  return `${cents / 100n}.${(cents % 100n).toString().padStart(2, '0')}`
}

function canComplete(renewal: Renewal) {
  return amountInMinorUnits(verifiedAmount(renewal.id)) >= amountInMinorUnits(renewal.agreed_price)
}

function formatMoney(amount: string | number, currency = 'IDR') {
  const value = Number(amount)
  return `${currency} ${Number.isFinite(value) ? value.toLocaleString('id-ID') : amount}`
}

function formatDate(value: string) {
  return new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString('id-ID', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'Asia/Jakarta',
  })
}

function statusStyle(status: string) {
  if (status === 'COMPLETED') return 'bg-emerald-50 text-emerald-700'
  if (status === 'REJECTED' || status === 'CANCELLED') return 'bg-slate-100 text-slate-500'
  if (status === 'APPROVED') return 'bg-sky-50 text-sky-700'
  return 'bg-amber-50 text-amber-700'
}

function errorMessage(value: unknown, fallback: string) {
  if (typeof value === 'object' && value !== null && 'response' in value) {
    const response = value.response
    if (typeof response === 'object' && response !== null && 'data' in response) {
      const data = response.data
      if (typeof data === 'object' && data !== null && 'detail' in data && typeof data.detail === 'string') {
        return data.detail
      }
    }
  }
  return fallback
}

async function fetchData() {
  loading.value = true
  error.value = ''
  try {
    const [renewalResponse, rentalResponse, paymentResponse, customerResponse] = await Promise.all([
      api.get('/renewals?page=1&page_size=100'),
      api.get('/rentals?page=1&page_size=100'),
      api.get('/payments?page=1&page_size=100'),
      api.get('/customers?page=1&page_size=100'),
    ])
    renewals.value = renewalResponse.data.items
    rentals.value = rentalResponse.data.items
    payments.value = paymentResponse.data.items
    customers.value = customerResponse.data.items
  } catch (cause) {
    error.value = errorMessage(cause, 'Data renewal dan pembayaran gagal dimuat.')
  } finally {
    loading.value = false
  }
}

function openOfferModal() {
  offerForm.value = {
    rental_id: '',
    offered_duration_value: 1,
    offered_duration_unit: 'MONTHS',
    offered_price: '',
    currency: 'IDR',
    renewal_model: 'CONTINUOUS',
    expires_in_hours: 72,
  }
  showOfferModal.value = true
}

function onOfferRentalChange() {
  const rental = rentalFor(offerForm.value.rental_id)
  offerForm.value.offered_price = rental?.agreed_price ?? ''
}

async function createOffer() {
  error.value = ''
  notice.value = ''
  saving.value = true
  try {
    await api.post('/renewal-offers', {
      ...offerForm.value,
      offered_duration_value: Number(offerForm.value.offered_duration_value),
      offered_price: offerForm.value.offered_price,
      expires_in_hours: Number(offerForm.value.expires_in_hours),
    })
    showOfferModal.value = false
    notice.value = 'Penawaran tersimpan. Penawaran aktif akan tampil pada reminder berikutnya bagi customer yang sudah memberi consent.'
    await fetchData()
  } catch (cause) {
    error.value = errorMessage(cause, 'Penawaran gagal dibuat.')
  } finally {
    saving.value = false
  }
}

function openApproval(renewal: Renewal) {
  selectedRenewal.value = renewal
  approvalForm.value = {
    renewal_model: renewal.renewal_model,
    confirmed_start_date: '',
  }
  showApprovalModal.value = true
}

async function approveRenewal() {
  if (!selectedRenewal.value) return
  if (approvalForm.value.renewal_model === 'IMMEDIATE' && !approvalForm.value.confirmed_start_date) {
    error.value = 'Tanggal mulai wajib dipilih untuk model immediate.'
    return
  }
  error.value = ''
  saving.value = true
  try {
    const payload: { renewal_model: string; confirmed_start_date?: string } = {
      renewal_model: approvalForm.value.renewal_model,
    }
    if (approvalForm.value.confirmed_start_date) {
      payload.confirmed_start_date = approvalForm.value.confirmed_start_date
    }
    await api.post(`/renewals/${selectedRenewal.value.id}/approve`, payload)
    showApprovalModal.value = false
    notice.value = 'Renewal disetujui. Rental belum berubah sampai pembayaran terverifikasi dan renewal diselesaikan.'
    await fetchData()
  } catch (cause) {
    error.value = errorMessage(cause, 'Renewal gagal disetujui.')
  } finally {
    saving.value = false
  }
}

async function rejectRenewal(renewal: Renewal) {
  if (!window.confirm('Tolak permintaan renewal ini?')) return
  error.value = ''
  try {
    await api.post(`/renewals/${renewal.id}/reject`)
    notice.value = 'Permintaan renewal ditolak.'
    await fetchData()
  } catch (cause) {
    error.value = errorMessage(cause, 'Renewal gagal ditolak.')
  }
}

function openPayment(renewal: Renewal) {
  selectedRenewal.value = renewal
  paymentForm.value = {
    amount: renewal.agreed_price,
    payment_method: 'BANK_TRANSFER',
    payment_reference: '',
  }
  showPaymentModal.value = true
}

async function createPayment() {
  const renewal = selectedRenewal.value
  const rental = renewal ? rentalFor(renewal.rental_id) : undefined
  if (!renewal || !rental) {
    error.value = 'Data rental tidak ditemukan untuk renewal ini.'
    return
  }
  error.value = ''
  saving.value = true
  try {
    const payload: Record<string, string> = {
      customer_id: rental.customer_id,
      rental_id: rental.id,
      renewal_id: renewal.id,
      amount: paymentForm.value.amount,
      currency: renewal.currency,
      payment_method: paymentForm.value.payment_method,
    }
    if (paymentForm.value.payment_reference.trim()) {
      payload.payment_reference = paymentForm.value.payment_reference.trim()
    }
    await api.post('/payments', payload)
    showPaymentModal.value = false
    notice.value = 'Pembayaran dicatat sebagai pending. Verifikasi setelah dana benar-benar diterima.'
    await fetchData()
  } catch (cause) {
    error.value = errorMessage(cause, 'Pembayaran gagal dicatat.')
  } finally {
    saving.value = false
  }
}

async function verifyPayment(payment: Payment) {
  if (!window.confirm('Konfirmasi dana sudah diterima untuk pembayaran ini?')) return
  error.value = ''
  try {
    await api.post(`/payments/${payment.id}/verify`)
    notice.value = 'Pembayaran berhasil diverifikasi.'
    await fetchData()
  } catch (cause) {
    error.value = errorMessage(cause, 'Pembayaran gagal diverifikasi.')
  }
}

async function completeRenewal(renewal: Renewal) {
  if (!canComplete(renewal)) {
    error.value = 'Jumlah pembayaran terverifikasi belum mencukupi harga renewal.'
    return
  }
  if (!window.confirm('Selesaikan renewal dan ubah masa berlaku rental sekarang?')) return
  error.value = ''
  try {
    await api.post(`/renewals/${renewal.id}/complete`)
    notice.value = 'Renewal selesai. Reminder baru dibuat dan reminder lama yang belum terkirim dibatalkan.'
    await fetchData()
  } catch (cause) {
    error.value = errorMessage(cause, 'Renewal belum dapat diselesaikan.')
  }
}

onMounted(fetchData)
</script>

<template>
  <AppLayout>
    <div class="animate-fade-up space-y-5">
      <header class="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p class="mb-1 text-[11px] font-bold uppercase tracking-[0.2em] text-[#1c1c1f]/35">Retensi & transaksi</p>
          <h1 class="bento-page-title">Renewal</h1>
          <p class="mt-1 text-sm text-[#1c1c1f]/45">Kelola penawaran, approval, dan pembayaran terverifikasi.</p>
        </div>
        <div class="flex flex-col gap-2 sm:flex-row">
          <button class="bento-white px-5 py-3 text-sm font-semibold" :disabled="loading" @click="fetchData">
            Muat ulang
          </button>
          <button class="bento-primary px-5 py-3 text-sm font-semibold" @click="openOfferModal">
            Buat penawaran
          </button>
        </div>
      </header>

      <div v-if="error" class="bento-white border border-rose-200 p-4 text-sm text-rose-700">{{ error }}</div>
      <div v-if="notice" class="bento-white border border-emerald-200 p-4 text-sm text-emerald-800">
        {{ notice }}
        <button class="ml-2 font-bold" @click="notice = ''">×</button>
      </div>

      <section class="grid gap-3 sm:grid-cols-3">
        <article class="bento-glass p-4">
          <p class="text-xs font-semibold uppercase tracking-wider text-[#1c1c1f]/40">Permintaan</p>
          <p class="mt-1 text-2xl font-bold text-[#1c1c1f]">{{ renewals.length }}</p>
        </article>
        <article class="bento-glass p-4">
          <p class="text-xs font-semibold uppercase tracking-wider text-amber-700/60">Menunggu review</p>
          <p class="mt-1 text-2xl font-bold text-amber-700">{{ pendingCount }}</p>
        </article>
        <article class="bento-glass p-4">
          <p class="text-xs font-semibold uppercase tracking-wider text-sky-700/60">Disetujui</p>
          <p class="mt-1 text-2xl font-bold text-sky-700">{{ approvedCount }}</p>
        </article>
      </section>

      <div v-if="loading" class="grid gap-3">
        <div v-for="item in 3" :key="item" class="h-36 animate-pulse rounded-[28px] bg-white/50" />
      </div>
      <div v-else-if="renewals.length === 0" class="bento-glass py-16 text-center">
        <p class="font-semibold text-[#1c1c1f]/70">Belum ada permintaan renewal</p>
        <p class="mt-1 text-sm text-[#1c1c1f]/40">Buat penawaran untuk dikirim pada reminder Telegram berikutnya.</p>
      </div>

      <div v-else class="space-y-3">
        <article v-for="renewal in renewals" :key="renewal.id" class="bento-white p-4 sm:p-5">
          <div class="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-full px-2.5 py-1 text-xs font-semibold" :class="statusStyle(renewal.status)">
                  {{ renewal.status }}
                </span>
                <span class="text-xs text-[#1c1c1f]/35">Rental {{ renewal.rental_id }}</span>
              </div>
              <p class="mt-3 text-sm font-semibold text-[#1c1c1f]">
                {{ renewal.duration_value }} {{ renewal.duration_unit.toLowerCase() }}
                · {{ formatMoney(renewal.agreed_price, renewal.currency) }}
              </p>
              <p class="mt-1 text-xs text-[#1c1c1f]/45">
                Periode baru {{ formatDate(renewal.new_start_date) }} — {{ formatDate(renewal.new_expiration_date) }}
                · model {{ renewal.renewal_model }}
              </p>
              <p class="mt-1 text-xs text-[#1c1c1f]/35">Permintaan {{ formatDate(renewal.created_at) }}</p>
            </div>
            <div class="flex flex-wrap gap-2">
              <template v-if="renewal.status === 'PENDING'">
                <button class="bento-primary px-4 py-2 text-xs font-semibold" @click="openApproval(renewal)">
                  Review & setujui
                </button>
                <button class="bento-white px-4 py-2 text-xs font-semibold text-rose-700" @click="rejectRenewal(renewal)">
                  Tolak
                </button>
              </template>
              <template v-if="renewal.status === 'APPROVED'">
                <button class="bento-white px-4 py-2 text-xs font-semibold" @click="openPayment(renewal)">
                  Catat pembayaran
                </button>
                <button
                  class="bento-primary px-4 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-40"
                  :disabled="!canComplete(renewal)"
                  @click="completeRenewal(renewal)"
                >
                  Selesaikan
                </button>
              </template>
            </div>
          </div>

          <div v-if="renewal.status === 'APPROVED'" class="mt-4 rounded-2xl bg-[#1c1c1f]/[0.035] p-3">
            <div class="flex flex-wrap justify-between gap-2 text-xs">
              <span class="text-[#1c1c1f]/50">Pembayaran terverifikasi</span>
              <span class="font-bold text-[#1c1c1f]">
                {{ formatMoney(verifiedAmount(renewal.id), renewal.currency) }}
                / {{ formatMoney(renewal.agreed_price, renewal.currency) }}
              </span>
            </div>
            <div v-for="payment in payments.filter((item) => item.renewal_id === renewal.id)" :key="payment.id"
              class="mt-2 flex flex-col justify-between gap-2 border-t border-[#1c1c1f]/[0.06] pt-2 text-xs sm:flex-row sm:items-center">
              <span class="text-[#1c1c1f]/65">
                {{ formatMoney(payment.amount, payment.currency) }} · {{ payment.payment_method }}
                <span v-if="payment.payment_reference">· {{ payment.payment_reference }}</span>
              </span>
              <div class="flex items-center gap-2">
                <span class="font-semibold" :class="payment.verified_at ? 'text-emerald-700' : 'text-amber-700'">
                  {{ payment.verified_at ? 'TERVERIFIKASI' : payment.status }}
                </span>
                <button v-if="payment.status === 'PENDING'" class="font-semibold underline" @click="verifyPayment(payment)">
                  Verifikasi
                </button>
              </div>
            </div>
          </div>
        </article>
      </div>
    </div>

    <Teleport to="body">
      <Transition name="bento-overlay">
        <div v-if="showOfferModal" class="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/35 p-0 backdrop-blur-md sm:items-center sm:p-4" @click.self="showOfferModal = false">
          <form class="bento-modal max-h-[92dvh] w-full space-y-4 overflow-y-auto rounded-t-[28px] p-6 sm:max-h-[calc(100dvh-2rem)] sm:max-w-lg sm:rounded-[28px]" @submit.prevent="createOffer">
            <div class="flex items-center justify-between">
              <h2 class="text-lg font-bold text-[#1c1c1f]">Buat penawaran renewal</h2>
              <button type="button" class="text-xl text-[#1c1c1f]/40" @click="showOfferModal = false">×</button>
            </div>
            <label class="block text-xs font-semibold text-[#1c1c1f]/60">
              Rental
              <select v-model="offerForm.rental_id" required class="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm" @change="onOfferRentalChange">
                <option value="" disabled>Pilih rental</option>
                <option v-for="rental in rentals" :key="rental.id" :value="rental.id">
                  {{ customerName(rental.customer_id) }} · {{ rental.status }} · berakhir {{ formatDate(rental.expiration_date) }}
                </option>
              </select>
            </label>
            <div class="grid grid-cols-2 gap-3">
              <label class="text-xs font-semibold text-[#1c1c1f]/60">
                Durasi
                <input v-model.number="offerForm.offered_duration_value" type="number" min="1" required class="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
              </label>
              <label class="text-xs font-semibold text-[#1c1c1f]/60">
                Unit
                <select v-model="offerForm.offered_duration_unit" class="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm">
                  <option value="DAYS">Hari</option><option value="WEEKS">Minggu</option>
                  <option value="MONTHS">Bulan</option><option value="YEARS">Tahun</option>
                </select>
              </label>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <label class="text-xs font-semibold text-[#1c1c1f]/60">
                Harga (IDR)
                <input v-model="offerForm.offered_price" type="number" min="0" step="1000" required class="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
              </label>
              <label class="text-xs font-semibold text-[#1c1c1f]/60">
                Berlaku (jam)
                <input v-model.number="offerForm.expires_in_hours" type="number" min="1" max="720" required class="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
              </label>
            </div>
            <label class="block text-xs font-semibold text-[#1c1c1f]/60">
              Model renewal yang ditawarkan
              <select v-model="offerForm.renewal_model" class="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm">
                <option value="CONTINUOUS">Continuous</option><option value="IMMEDIATE">Immediate (admin konfirmasi tanggal saat review)</option>
              </select>
            </label>
            <p class="rounded-xl bg-amber-50 p-3 text-xs leading-5 text-amber-800">
              Penawaran dikirim pada reminder berikutnya jika customer telah menautkan akun dan memberi consent.
            </p>
            <button class="bento-primary w-full py-3 text-sm font-semibold disabled:opacity-50" :disabled="saving">
              {{ saving ? 'Menyimpan...' : 'Simpan penawaran' }}
            </button>
          </form>
        </div>
      </Transition>

      <Transition name="bento-overlay">
        <div v-if="showApprovalModal && selectedRenewal" class="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/35 p-0 backdrop-blur-md sm:items-center sm:p-4" @click.self="showApprovalModal = false">
          <form class="bento-modal w-full space-y-4 rounded-t-[28px] p-6 sm:max-w-md sm:rounded-[28px]" @submit.prevent="approveRenewal">
            <div class="flex items-center justify-between">
              <h2 class="text-lg font-bold text-[#1c1c1f]">Review renewal</h2>
              <button type="button" class="text-xl text-[#1c1c1f]/40" @click="showApprovalModal = false">×</button>
            </div>
            <p class="text-sm text-[#1c1c1f]/55">
              {{ selectedRenewal.duration_value }} {{ selectedRenewal.duration_unit.toLowerCase() }} ·
              {{ formatMoney(selectedRenewal.agreed_price, selectedRenewal.currency) }}
            </p>
            <label class="block text-xs font-semibold text-[#1c1c1f]/60">
              Model renewal
              <select v-model="approvalForm.renewal_model" class="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm">
                <option value="CONTINUOUS">Continuous</option><option value="IMMEDIATE">Immediate</option>
              </select>
            </label>
            <label v-if="approvalForm.renewal_model === 'IMMEDIATE'" class="block text-xs font-semibold text-[#1c1c1f]/60">
              Tanggal mulai terkonfirmasi
              <input v-model="approvalForm.confirmed_start_date" type="date" required class="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
            </label>
            <p class="rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-600">
              Approval tidak mengubah rental. Catat dan verifikasi pembayaran, lalu pilih Selesaikan.
            </p>
            <button class="bento-primary w-full py-3 text-sm font-semibold disabled:opacity-50" :disabled="saving">
              {{ saving ? 'Memproses...' : 'Setujui renewal' }}
            </button>
          </form>
        </div>
      </Transition>

      <Transition name="bento-overlay">
        <div v-if="showPaymentModal && selectedRenewal" class="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/35 p-0 backdrop-blur-md sm:items-center sm:p-4" @click.self="showPaymentModal = false">
          <form class="bento-modal w-full space-y-4 rounded-t-[28px] p-6 sm:max-w-md sm:rounded-[28px]" @submit.prevent="createPayment">
            <div class="flex items-center justify-between">
              <h2 class="text-lg font-bold text-[#1c1c1f]">Catat pembayaran</h2>
              <button type="button" class="text-xl text-[#1c1c1f]/40" @click="showPaymentModal = false">×</button>
            </div>
            <label class="block text-xs font-semibold text-[#1c1c1f]/60">
              Jumlah
              <input v-model="paymentForm.amount" type="number" min="1" step="1000" required class="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
            </label>
            <label class="block text-xs font-semibold text-[#1c1c1f]/60">
              Metode
              <select v-model="paymentForm.payment_method" class="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm">
                <option value="BANK_TRANSFER">Transfer bank</option><option value="QRIS">QRIS</option>
                <option value="EWALLET">E-wallet</option><option value="CASH">Tunai</option>
                <option value="MANUAL_OTHER">Lainnya</option>
              </select>
            </label>
            <label class="block text-xs font-semibold text-[#1c1c1f]/60">
              Referensi (opsional)
              <input v-model="paymentForm.payment_reference" maxlength="128" class="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
            </label>
            <p class="rounded-xl bg-amber-50 p-3 text-xs leading-5 text-amber-800">
              Pembayaran baru berstatus pending. Verifikasi hanya setelah dana benar-benar diterima.
            </p>
            <button class="bento-primary w-full py-3 text-sm font-semibold disabled:opacity-50" :disabled="saving">
              {{ saving ? 'Menyimpan...' : 'Catat sebagai pending' }}
            </button>
          </form>
        </div>
      </Transition>
    </Teleport>
  </AppLayout>
</template>
