<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '@/lib/api'
import AppLayout from '@/components/AppLayout.vue'

interface ProductVariant {
  id: string
  name: string
  duration_value: number
  duration_unit: string
  default_price: string
  currency: string
  status: string
}

interface Product {
  id: string
  name: string
  category: string
  has_profile_pin: boolean
  status: string
  variants: ProductVariant[]
}

interface Customer {
  id: string
  display_name: string
  telegram_username: string | null
  status: string
}

interface Rental {
  id: string
  customer_id: string
  product_id: string
  product_variant_id: string
  customer_display_name: string | null
  product_name: string | null
  product_variant_name: string | null
  start_date: string
  expiration_date: string
  duration_value: number
  duration_unit: string
  agreed_price: string
  currency: string
  account_email: string | null
  profile: string | null
  pin: string | null
  status: string
  effective_status: string
  warning_state: string
  days_remaining: number
  renewal_model: string
  created_at: string
}

const rentals = ref<Rental[]>([])
const customers = ref<Customer[]>([])
const products = ref<Product[]>([])
const formDataLoaded = ref(false)
const loadingFormData = ref(false)
const loading = ref(true)
const error = ref('')

// Modal state
const showAddRental = ref(false)
const addingRental = ref(false)
const editingRentalId = ref<string | null>(null)
const rentalError = ref('')
const revealedPins = ref(new Set<string>())
let rentalFormDataRequest: Promise<void> | null = null

const rentalForm = ref({
  customer_id: '',
  product_id: '',
  product_variant_id: '',
  start_date: new Date().toISOString().split('T')[0],
  expiration_date: '',
  duration_value: 1,
  duration_unit: 'MONTHS',
  agreed_price: '',
  account_email: '',
  profile: '',
  pin: '',
  renewal_model: 'CONTINUOUS',
  status: 'ACTIVE',
})

const availableVariants = computed(() => {
  if (!rentalForm.value.product_id) return []
  const p = products.value.find((prod) => prod.id === rentalForm.value.product_id)
  return p ? p.variants : []
})

const selectedProduct = computed(() =>
  products.value.find((product) => product.id === rentalForm.value.product_id) ?? null,
)

function onProductChange() {
  rentalForm.value.product_variant_id = ''
  rentalForm.value.agreed_price = ''
  if (!selectedProduct.value?.has_profile_pin) {
    rentalForm.value.profile = ''
    rentalForm.value.pin = ''
  }
}

function onVariantChange() {
  const v = availableVariants.value.find((item) => item.id === rentalForm.value.product_variant_id)
  if (v) {
    rentalForm.value.agreed_price = v.default_price
    rentalForm.value.duration_value = v.duration_value
    rentalForm.value.duration_unit = v.duration_unit
  } else {
    rentalForm.value.agreed_price = ''
  }
}

async function loadRentalFormData() {
  if (formDataLoaded.value) return
  if (rentalFormDataRequest) return rentalFormDataRequest
  loadingFormData.value = true
  rentalFormDataRequest = Promise.all([
    api.get('/customers?page=1&page_size=100'),
    api.get('/products?page=1&page_size=100'),
  ])
    .then(([customerResponse, productResponse]) => {
      customers.value = customerResponse.data.items
      products.value = productResponse.data.items
      formDataLoaded.value = true
    })
    .finally(() => {
      loadingFormData.value = false
      rentalFormDataRequest = null
    })
  return rentalFormDataRequest
}

async function openAddRental() {
  editingRentalId.value = null
  rentalError.value = ''
  rentalForm.value = {
    customer_id: '',
    product_id: '',
    product_variant_id: '',
    start_date: new Date().toISOString().split('T')[0],
    expiration_date: '',
    duration_value: 1,
    duration_unit: 'MONTHS',
    agreed_price: '',
    account_email: '',
    profile: '',
    pin: '',
    renewal_model: 'CONTINUOUS',
    status: 'ACTIVE',
  }
  showAddRental.value = true
  try {
    await loadRentalFormData()
  } catch (cause: any) {
    rentalError.value = cause.response?.data?.detail ?? 'Gagal memuat customer dan produk.'
  }
}

async function openEditRental(rental: Rental) {
  rentalError.value = ''
  showAddRental.value = true
  try {
    await loadRentalFormData()
  } catch (cause: any) {
    rentalError.value = cause.response?.data?.detail ?? 'Gagal memuat customer dan produk.'
    return
  }
  editingRentalId.value = rental.id
  rentalForm.value = {
    customer_id: rental.customer_id,
    product_id: rental.product_id,
    product_variant_id: rental.product_variant_id,
    start_date: rental.start_date,
    expiration_date: rental.expiration_date,
    duration_value: rental.duration_value,
    duration_unit: rental.duration_unit,
    agreed_price: rental.agreed_price,
    account_email: rental.account_email ?? '',
    profile: rental.profile ?? '',
    pin: rental.pin ?? '',
    renewal_model: rental.renewal_model,
    status: rental.status,
  }
  showAddRental.value = true
}

async function fetchData() {
  loading.value = true
  error.value = ''
  try {
    const response = await api.get('/rentals?page=1&page_size=100')
    rentals.value = response.data.items
  } catch (e: any) {
    error.value = e.response?.data?.detail ?? 'Gagal memuat data rental.'
  } finally {
    loading.value = false
  }
}

async function submitRental() {
  rentalError.value = ''
  addingRental.value = true
  try {
    if (!rentalForm.value.customer_id) {
      throw new Error('Pilih customer terlebih dahulu.')
    }
    if (!rentalForm.value.product_id || !rentalForm.value.product_variant_id) {
      throw new Error('Pilih produk dan varian yang akan disewa.')
    }

    const payload: any = {
      customer_id: rentalForm.value.customer_id,
      product_id: rentalForm.value.product_id,
      product_variant_id: rentalForm.value.product_variant_id,
      start_date: rentalForm.value.start_date,
      renewal_model: rentalForm.value.renewal_model,
      account_email: rentalForm.value.account_email.trim() || null,
    }
    if (selectedProduct.value?.has_profile_pin) {
      payload.profile = rentalForm.value.profile.trim() || null
      payload.pin = rentalForm.value.pin.trim() || null
    } else if (editingRentalId.value) {
      payload.profile = null
      payload.pin = null
    }
    if (rentalForm.value.agreed_price) {
      payload.agreed_price = rentalForm.value.agreed_price
    }

    if (editingRentalId.value) {
      await api.patch(`/rentals/${editingRentalId.value}`, {
        ...payload,
        expiration_date: rentalForm.value.expiration_date,
        duration_value: Number(rentalForm.value.duration_value),
        duration_unit: rentalForm.value.duration_unit,
        status: rentalForm.value.status,
      })
    } else {
      await api.post('/rentals', payload)
    }
    showAddRental.value = false
    editingRentalId.value = null
    rentalForm.value = {
      customer_id: '',
      product_id: '',
      product_variant_id: '',
      start_date: new Date().toISOString().split('T')[0],
      expiration_date: '',
      duration_value: 1,
      duration_unit: 'MONTHS',
      agreed_price: '',
      account_email: '',
      profile: '',
      pin: '',
      renewal_model: 'CONTINUOUS',
      status: 'ACTIVE',
    }
    await fetchData()
  } catch (e: any) {
    rentalError.value = e.response?.data?.detail || e.message || 'Gagal membuat rental.'
  } finally {
    addingRental.value = false
  }
}

async function archiveRental(rental: Rental) {
  if (!window.confirm('Arsipkan data rental ini? Riwayat transaksi dan notifikasinya tetap disimpan.')) return
  try {
    await api.post(`/rentals/${rental.id}/archive`)
    await fetchData()
  } catch (cause: any) {
    error.value = cause.response?.data?.detail ?? 'Gagal mengarsipkan rental. Rental aktif harus dibatalkan terlebih dahulu.'
  }
}

function statusBadge(status: string) {
  if (status === 'ACTIVE') return 'bg-[#1c1c1f] text-white'
  if (status === 'SCHEDULED') return 'bg-[#1c1c1f]/[0.06] text-[#1c1c1f]/65'
  if (status === 'EXPIRING_SOON') return 'bg-[#1c1c1f]/[0.14] text-[#1c1c1f]'
  if (status === 'EXPIRED') return 'bg-[#1c1c1f]/[0.06] text-[#1c1c1f]/45'
  return 'bg-slate-100 text-slate-600'
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' })
}

function togglePin(rentalId: string) {
  const updated = new Set(revealedPins.value)
  if (updated.has(rentalId)) updated.delete(rentalId)
  else updated.add(rentalId)
  revealedPins.value = updated
}

onMounted(fetchData)
</script>

<template>
  <AppLayout>
    <div class="mb-6 flex animate-fade-up flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="mb-1 text-[11px] font-bold uppercase tracking-[0.2em] text-[#1c1c1f]/35">Transaksi</p>
        <h1 class="bento-page-title">Rental</h1>
        <p class="mt-1 text-sm text-[#1c1c1f]/45">Pantau customer, periode sewa, dan masa aktif.</p>
      </div>
      <button
        @click="openAddRental"
        class="bento-primary inline-flex w-full items-center justify-center gap-2 px-5 py-3 text-sm font-semibold sm:w-auto"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        Tambah Rental
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="space-y-3">
      <div v-for="i in 4" :key="i" class="h-24 animate-pulse rounded-[28px] bg-white/50 p-5">
        <div class="h-4 bg-gray-200 rounded w-1/4 mb-2"></div>
        <div class="h-3 bg-gray-100 rounded w-1/3"></div>
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="bento-white border border-rose-200 p-4 text-sm text-rose-700">{{ error }}</div>

    <!-- Empty -->
    <div v-else-if="rentals.length === 0" class="bento-glass py-16 text-center text-[#1c1c1f]/45">
      <svg class="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
      </svg>
      <p class="font-medium">Belum ada transaksi rental</p>
      <p class="text-sm mt-1">Klik "Tambah Rental" untuk mulai transaksi sewa</p>
    </div>

    <!-- Table -->
    <div v-else class="bento-white animate-fade-up overflow-hidden">
      <div class="hidden overflow-x-auto sm:block">
        <table class="w-full min-w-[840px] text-sm">
          <thead>
            <tr class="border-b border-gray-100 text-xs text-gray-400 uppercase tracking-wider">
              <th class="text-left px-6 py-3 font-medium">Customer</th>
              <th class="text-left px-6 py-3 font-medium">Produk & Varian</th>
              <th class="text-left px-6 py-3 font-medium">Periode Sewa</th>
              <th class="text-left px-6 py-3 font-medium">Harga Kesepakatan</th>
              <th class="text-left px-6 py-3 font-medium">Status Efektif</th>
              <th class="px-6 py-3 font-medium">Aksi</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-[#1c1c1f]/[0.05]">
            <tr v-for="r in rentals" :key="r.id" class="transition-colors hover:bg-[#1c1c1f]/[0.025]">
              <td class="px-6 py-4 font-semibold text-gray-900">
                {{ r.customer_display_name || 'Customer #' + r.customer_id.slice(0, 8) }}
              </td>
              <td class="px-6 py-4 text-gray-700">
                <span class="font-medium text-gray-900">{{ r.product_name || 'Produk' }}</span>
                <span class="text-xs text-gray-500 block">Varian: {{ r.product_variant_name || r.duration_value + ' ' + r.duration_unit.toLowerCase() }}</span>
                <span v-if="r.account_email" class="mt-1 block text-xs text-gray-500">
                  Akun: {{ r.account_email }}
                </span>
                <span v-if="r.profile || r.pin" class="mt-1 block text-xs text-gray-500">
                  Profile: {{ r.profile || '—' }} · PIN:
                  <span class="font-mono">{{ revealedPins.has(r.id) ? r.pin : '••••' }}</span>
                  <button
                    type="button"
                    class="ml-1 font-semibold text-[#1c1c1f]/70 underline"
                    :aria-label="revealedPins.has(r.id) ? 'Sembunyikan PIN' : 'Tampilkan PIN'"
                    @click="togglePin(r.id)"
                  >
                    {{ revealedPins.has(r.id) ? 'Sembunyikan' : 'Lihat' }}
                  </button>
                </span>
              </td>
              <td class="px-6 py-4 text-gray-600 text-xs">
                <div>Mulai: {{ formatDate(r.start_date) }}</div>
                <div class="font-medium text-slate-800">Kedaluwarsa: {{ formatDate(r.expiration_date) }}</div>
                <div class="text-[11px] text-gray-400">Sisa {{ r.days_remaining }} hari</div>
              </td>
              <td class="px-6 py-4 font-medium text-gray-900">
                {{ r.currency }} {{ Number(r.agreed_price).toLocaleString('id-ID') }}
              </td>
              <td class="px-6 py-4">
                <span class="text-xs px-2.5 py-1 rounded-full font-semibold" :class="statusBadge(r.effective_status)">
                  {{ r.effective_status }}
                </span>
                <span v-if="r.warning_state !== 'NONE'" class="block mt-1 text-[11px] font-medium text-amber-600">
                  {{ r.warning_state }}
                </span>
              </td>
              <td class="px-6 py-4">
                <div class="flex justify-end gap-2">
                  <button class="rounded-full border border-[#1c1c1f]/10 px-3 py-1.5 text-xs font-semibold" @click="openEditRental(r)">Edit</button>
                  <button class="rounded-full border border-rose-200 px-3 py-1.5 text-xs font-semibold text-rose-700" @click="archiveRental(r)">Arsipkan</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Mobile List -->
      <div class="divide-y divide-slate-100 sm:hidden">
        <article v-for="r in rentals" :key="r.id" class="space-y-2 p-4">
          <div class="flex items-start justify-between gap-2">
            <div>
              <h2 class="text-sm font-semibold text-slate-900">{{ r.customer_display_name || 'Customer' }}</h2>
              <p class="text-xs text-slate-600">{{ r.product_name }} - {{ r.product_variant_name }}</p>
              <p v-if="r.account_email" class="break-all text-xs text-slate-500">Akun: {{ r.account_email }}</p>
              <p v-if="r.profile || r.pin" class="text-xs text-slate-500">
                Profile: {{ r.profile || '—' }} · PIN:
                <span class="font-mono">{{ revealedPins.has(r.id) ? r.pin : '••••' }}</span>
                <button type="button" class="ml-1 underline" @click="togglePin(r.id)">
                  {{ revealedPins.has(r.id) ? 'Sembunyikan' : 'Lihat' }}
                </button>
              </p>
            </div>
            <span class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold" :class="statusBadge(r.effective_status)">
              {{ r.effective_status }}
            </span>
          </div>
          <div class="text-xs text-slate-500 flex justify-between">
            <span>{{ formatDate(r.start_date) }} - {{ formatDate(r.expiration_date) }}</span>
            <span class="font-semibold text-slate-800">{{ r.currency }} {{ Number(r.agreed_price).toLocaleString('id-ID') }}</span>
          </div>
          <div class="grid grid-cols-2 gap-2 pt-1">
            <button class="rounded-full border border-[#1c1c1f]/10 px-3 py-2 text-xs font-semibold" @click="openEditRental(r)">Edit</button>
            <button class="rounded-full border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700" @click="archiveRental(r)">Arsipkan</button>
          </div>
        </article>
      </div>
    </div>

    <!-- Modal: Add Rental -->
    <Teleport to="body">
      <Transition name="bento-overlay">
      <div v-if="showAddRental" class="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/35 p-0 backdrop-blur-md sm:items-center sm:p-4" @click.self="showAddRental = false">
        <div class="bento-modal max-h-[92dvh] w-full overflow-y-auto rounded-t-[28px] sm:max-h-[calc(100dvh-2rem)] sm:max-w-md sm:rounded-[28px]">
          <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100">
            <h3 class="font-semibold text-gray-900">{{ editingRentalId ? 'Edit Rental' : 'Tambah Rental Baru' }}</h3>
            <button @click="showAddRental = false" class="text-gray-400 hover:text-gray-600">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <form @submit.prevent="submitRental" class="bento-form space-y-4 px-6 py-5">
            <div v-if="rentalError" class="bg-red-50 border border-red-200 text-red-600 text-sm rounded-lg px-3 py-2">{{ rentalError }}</div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Customer <span class="text-red-500">*</span></label>
              <select
                v-model="rentalForm.customer_id"
                required
                :disabled="loadingFormData"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="" disabled>{{ loadingFormData ? 'Memuat customer...' : '-- Pilih Customer --' }}</option>
                <option v-for="c in customers" :key="c.id" :value="c.id">
                  {{ c.display_name }} ({{ c.telegram_username ? '@' + c.telegram_username : 'No Telegram' }})
                </option>
              </select>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Produk <span class="text-red-500">*</span></label>
              <select
                v-model="rentalForm.product_id"
                @change="onProductChange"
                required
                :disabled="loadingFormData"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="" disabled>{{ loadingFormData ? 'Memuat produk...' : '-- Pilih Produk --' }}</option>
                <option v-for="p in products" :key="p.id" :value="p.id">
                  {{ p.name }} ({{ p.category }})
                </option>
              </select>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Varian Produk <span class="text-red-500">*</span></label>
              <select
                v-model="rentalForm.product_variant_id"
                @change="onVariantChange"
                :disabled="!rentalForm.product_id"
                required
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-gray-100 disabled:text-gray-400"
              >
                <option value="" disabled>
                  {{ rentalForm.product_id ? '-- Pilih Varian --' : '-- Pilih Produk Dahulu --' }}
                </option>
                <option v-for="v in availableVariants" :key="v.id" :value="v.id">
                  {{ v.name }} - {{ v.duration_value }} {{ v.duration_unit.toLowerCase() }} ({{ v.currency }} {{ Number(v.default_price).toLocaleString('id-ID') }})
                </option>
              </select>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Tanggal Mulai <span class="text-red-500">*</span></label>
                <input
                  v-model="rentalForm.start_date"
                  type="date"
                  required
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Model Renewal</label>
                <select
                  v-model="rentalForm.renewal_model"
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="CONTINUOUS">Continuous</option>
                  <option value="IMMEDIATE">Immediate</option>
                </select>
              </div>
              <div v-if="editingRentalId">
                <label class="block text-sm font-medium text-gray-700 mb-1">Tanggal Berakhir *</label>
                <input v-model="rentalForm.expiration_date" type="date" required
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
            </div>

            <div v-if="editingRentalId" class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Durasi</label>
                <input v-model.number="rentalForm.duration_value" type="number" min="1" required
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Satuan Durasi</label>
                <select v-model="rentalForm.duration_unit" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                  <option value="DAYS">Hari</option>
                  <option value="WEEKS">Minggu</option>
                  <option value="MONTHS">Bulan</option>
                  <option value="YEARS">Tahun</option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Status</label>
                <select v-model="rentalForm.status" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                  <option value="ACTIVE">Aktif</option>
                  <option value="SCHEDULED">Terjadwal</option>
                  <option value="CANCELLED">Dibatalkan</option>
                  <option v-if="rentalForm.status === 'EXPIRED'" value="EXPIRED">Expired</option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Model Renewal</label>
                <select v-model="rentalForm.renewal_model" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                  <option value="CONTINUOUS">Continuous</option>
                  <option value="IMMEDIATE">Immediate</option>
                </select>
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Harga Kesepakatan (IDR)</label>
              <input
                v-model="rentalForm.agreed_price"
                type="number"
                min="0"
                step="1000"
                placeholder="Default harga varian"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div class="space-y-3 rounded-xl border border-gray-200 p-3">
              <p class="text-xs font-semibold uppercase tracking-wide text-gray-500">Detail akun (opsional)</p>
              <div>
                <label class="mb-1 block text-sm font-medium text-gray-700">Email akun</label>
                <input
                  v-model="rentalForm.account_email"
                  type="email"
                  maxlength="320"
                  autocomplete="off"
                  placeholder="email akun produk"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div v-if="selectedProduct?.has_profile_pin" class="grid grid-cols-2 gap-3">
                <div>
                  <label class="mb-1 block text-sm font-medium text-gray-700">Profile</label>
                  <input
                    v-model="rentalForm.profile"
                    type="text"
                    maxlength="160"
                    autocomplete="off"
                    placeholder="Nama profile"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-gray-700">PIN</label>
                  <input
                    v-model="rentalForm.pin"
                    type="password"
                    maxlength="64"
                    autocomplete="new-password"
                    placeholder="PIN profile"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>
              <p v-if="selectedProduct?.has_profile_pin" class="text-xs text-gray-500">
                Profile dan PIN tersimpan terenkripsi.
              </p>
            </div>

            <div class="flex gap-3 pt-2">
              <button
                type="button"
                @click="showAddRental = false"
                class="flex-1 border border-gray-300 text-gray-700 text-sm font-medium py-2 rounded-lg hover:bg-gray-50 transition"
              >
                Batal
              </button>
              <button
                type="submit"
                :disabled="addingRental"
                class="bento-primary flex-1 py-2.5 text-sm font-semibold disabled:opacity-50"
              >
                {{ addingRental ? 'Menyimpan...' : 'Simpan' }}
              </button>
            </div>
          </form>
        </div>
      </div>
      </Transition>
    </Teleport>
  </AppLayout>
</template>
