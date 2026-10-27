<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
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
  status: string
  variants: ProductVariant[]
}

interface Customer {
  id: string
  display_name: string
  telegram_username: string | null
  telegram_user_id: number | null
  status: string
  internal_notes: string | null
  created_at: string
}

const customers = ref<Customer[]>([])
const products = ref<Product[]>([])
const productsLoaded = ref(false)
const loadingProducts = ref(false)
const loading = ref(true)
const error = ref('')

// Modal add customer
const showAddCustomer = ref(false)
const addingCustomer = ref(false)
const editingCustomerId = ref<string | null>(null)
const customerForm = ref({
  display_name: '',
  telegram_username: '',
  status: 'ACTIVE',
  internal_notes: '',
  assign_rental: false,
  product_id: '',
  product_variant_id: '',
  start_date: new Date().toISOString().split('T')[0],
  agreed_price: '',
  renewal_model: 'CONTINUOUS',
})
const customerError = ref('')
const showTelegramLink = ref(false)
const linkCommand = ref('')
const linkExpiresAt = ref('')
const linkCustomerName = ref('')
const linkError = ref('')
const creatingLink = ref(false)
let productsRequest: Promise<void> | null = null

const availableVariants = computed(() => {
  if (!customerForm.value.product_id) return []
  const p = products.value.find((prod) => prod.id === customerForm.value.product_id)
  return p ? p.variants : []
})

function onProductChange() {
  customerForm.value.product_variant_id = ''
  customerForm.value.agreed_price = ''
}

async function loadProductsForRental() {
  if (productsLoaded.value) return
  if (productsRequest) return productsRequest
  loadingProducts.value = true
  productsRequest = api.get('/products?page=1&page_size=100')
    .then((response) => {
      products.value = response.data.items
      productsLoaded.value = true
    })
    .catch((cause: any) => {
      customerError.value = cause.response?.data?.detail ?? 'Gagal memuat daftar produk.'
      throw cause
    })
    .finally(() => {
      loadingProducts.value = false
      productsRequest = null
    })
  return productsRequest
}

function onVariantChange() {
  const v = availableVariants.value.find((item) => item.id === customerForm.value.product_variant_id)
  if (v) {
    customerForm.value.agreed_price = v.default_price
  } else {
    customerForm.value.agreed_price = ''
  }
}

function openAddCustomer() {
  editingCustomerId.value = null
  customerError.value = ''
  customerForm.value = {
    display_name: '',
    telegram_username: '',
    status: 'ACTIVE',
    internal_notes: '',
    assign_rental: false,
    product_id: '',
    product_variant_id: '',
    start_date: new Date().toISOString().split('T')[0],
    agreed_price: '',
    renewal_model: 'CONTINUOUS',
  }
  showAddCustomer.value = true
}

async function fetchCustomers() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.get('/customers?page=1&page_size=100')
    customers.value = res.data.items
  } catch (e: any) {
    error.value = e.response?.data?.detail ?? 'Gagal memuat customer.'
  } finally {
    loading.value = false
  }
}

async function submitCustomer() {
  customerError.value = ''
  addingCustomer.value = true
  try {
    const payload: any = {
      display_name: customerForm.value.display_name.trim(),
      status: customerForm.value.status,
    }
    if (editingCustomerId.value) {
      payload.telegram_username = customerForm.value.telegram_username.trim() || null
      payload.internal_notes = customerForm.value.internal_notes.trim() || null
    } else {
      if (customerForm.value.telegram_username.trim()) payload.telegram_username = customerForm.value.telegram_username.trim()
      if (customerForm.value.internal_notes.trim()) payload.internal_notes = customerForm.value.internal_notes.trim()
    }

    let createdCustomer: Customer | null = null
    if (editingCustomerId.value) {
      await api.patch(`/customers/${editingCustomerId.value}`, payload)
    } else {
      const res = await api.post('/customers', payload)
      createdCustomer = res.data
    }

    if (customerForm.value.assign_rental && createdCustomer) {
      if (!customerForm.value.product_id || !customerForm.value.product_variant_id) {
        throw new Error('Pilih produk dan varian yang akan disewa.')
      }
      const rentalPayload: any = {
        customer_id: createdCustomer.id,
        product_id: customerForm.value.product_id,
        product_variant_id: customerForm.value.product_variant_id,
        start_date: customerForm.value.start_date,
        renewal_model: customerForm.value.renewal_model,
      }
      if (customerForm.value.agreed_price) {
        rentalPayload.agreed_price = customerForm.value.agreed_price
      }
      await api.post('/rentals', rentalPayload)
    }

    showAddCustomer.value = false
    editingCustomerId.value = null
    customerForm.value = {
      display_name: '',
      telegram_username: '',
      status: 'ACTIVE',
      internal_notes: '',
      assign_rental: false,
      product_id: '',
      product_variant_id: '',
      start_date: new Date().toISOString().split('T')[0],
      agreed_price: '',
      renewal_model: 'CONTINUOUS',
    }
    await fetchCustomers()
  } catch (e: any) {
    customerError.value = e.response?.data?.detail || e.message || 'Gagal menambah customer.'
  } finally {
    addingCustomer.value = false
  }
}

function openEditCustomer(customer: Customer) {
  editingCustomerId.value = customer.id
  customerForm.value = {
    display_name: customer.display_name,
    telegram_username: customer.telegram_username ?? '',
    status: customer.status,
    internal_notes: customer.internal_notes ?? '',
    assign_rental: false,
    product_id: '',
    product_variant_id: '',
    start_date: new Date().toISOString().split('T')[0],
    agreed_price: '',
    renewal_model: 'CONTINUOUS',
  }
  customerError.value = ''
  showAddCustomer.value = true
}

async function archiveCustomer(customer: Customer) {
  if (!window.confirm(`Arsipkan customer "${customer.display_name}"? Data dan riwayat rental tetap disimpan.`)) return
  try {
    await api.post(`/customers/${customer.id}/archive`)
    await fetchCustomers()
  } catch (cause: any) {
    error.value = cause.response?.data?.detail ?? 'Gagal mengarsipkan customer.'
  }
}

async function createTelegramLink(customer: Customer) {
  creatingLink.value = true
  linkError.value = ''
  linkCommand.value = ''
  try {
    const response = await api.post(`/customers/${customer.id}/telegram-link-token`)
    linkCommand.value = response.data.deep_link_command
    linkExpiresAt.value = response.data.expires_at
    linkCustomerName.value = customer.display_name
    showTelegramLink.value = true
  } catch (e: any) {
    linkError.value = e.response?.data?.detail ?? 'Gagal membuat tautan Telegram.'
    error.value = linkError.value
  } finally {
    creatingLink.value = false
  }
}

async function copyTelegramCommand() {
  try {
    await navigator.clipboard.writeText(linkCommand.value)
    linkError.value = 'Perintah tautan berhasil disalin.'
  } catch {
    linkError.value = 'Salin perintah secara manual dari kolom di atas.'
  }
}

function statusBadge(status: string) {
  if (status === 'ACTIVE') return 'bg-[#1c1c1f] text-white'
  if (status === 'INACTIVE') return 'bg-[#1c1c1f]/[0.07] text-[#1c1c1f]/55'
  if (status === 'SUSPENDED') return 'bg-[#1c1c1f]/[0.12] text-[#1c1c1f]/75'
  return 'bg-[#1c1c1f]/[0.05] text-[#1c1c1f]/40'
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' })
}

onMounted(fetchCustomers)
watch(
  () => customerForm.value.assign_rental,
  (enabled) => {
    if (enabled) void loadProductsForRental().catch(() => undefined)
  },
)
</script>

<template>
  <AppLayout>
    <div class="mb-6 flex animate-fade-up flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="mb-1 text-[11px] font-bold uppercase tracking-[0.2em] text-[#1c1c1f]/35">Relasi bisnis</p>
        <h1 class="bento-page-title">Customer</h1>
        <p class="mt-1 text-sm text-[#1c1c1f]/45">Profil pelanggan, akun Telegram, dan catatan.</p>
      </div>
      <button
        @click="openAddCustomer"
        class="bento-primary inline-flex w-full items-center justify-center gap-2 px-5 py-3 text-sm font-semibold sm:w-auto"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        Tambah Customer
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
    <div v-else-if="customers.length === 0" class="bento-glass py-16 text-center text-[#1c1c1f]/45">
      <svg class="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
          d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
      <p class="font-medium">Belum ada customer</p>
      <p class="text-sm mt-1">Klik "Tambah Customer" untuk mulai</p>
    </div>

    <!-- Table -->
    <div v-else class="bento-white animate-fade-up overflow-hidden">
      <div class="hidden overflow-x-auto sm:block">
      <table class="w-full min-w-[760px] text-sm">
        <thead>
          <tr class="border-b border-gray-100 text-xs text-gray-400 uppercase tracking-wider">
            <th class="text-left px-6 py-3 font-medium">Nama</th>
            <th class="text-left px-6 py-3 font-medium">Telegram</th>
            <th class="text-left px-6 py-3 font-medium">Status</th>
            <th class="text-left px-6 py-3 font-medium">Catatan</th>
            <th class="text-left px-6 py-3 font-medium">Bergabung</th>
            <th class="px-6 py-3 font-medium">Aksi</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-[#1c1c1f]/[0.05]">
          <tr v-for="c in customers" :key="c.id" class="transition-colors hover:bg-[#1c1c1f]/[0.025]">
            <td class="px-6 py-4 font-medium text-gray-900">{{ c.display_name }}</td>
            <td class="px-6 py-4 text-gray-500">
              <span v-if="c.telegram_username">@{{ c.telegram_username }}</span>
              <span v-else class="text-gray-300 italic">—</span>
            </td>
            <td class="px-6 py-4">
              <span class="text-xs px-2 py-0.5 rounded-full font-medium" :class="statusBadge(c.status)">
                {{ c.status }}
              </span>
            </td>
            <td class="px-6 py-4 text-gray-500 max-w-xs truncate">
              <span v-if="c.internal_notes">{{ c.internal_notes }}</span>
              <span v-else class="text-gray-300 italic">—</span>
            </td>
            <td class="px-6 py-4 text-gray-400">{{ formatDate(c.created_at) }}</td>
            <td class="px-6 py-4">
              <div class="flex justify-end gap-2">
                <button class="rounded-full border border-[#1c1c1f]/10 px-3 py-1.5 text-xs font-semibold" @click="openEditCustomer(c)">Edit</button>
                <button class="rounded-full border border-rose-200 px-3 py-1.5 text-xs font-semibold text-rose-700" @click="archiveCustomer(c)">Arsipkan</button>
                <button
                  class="rounded-full bg-[#1c1c1f] px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                  :disabled="creatingLink"
                  @click="createTelegramLink(c)"
                >
                  {{ c.telegram_user_id ? 'Tautkan ulang' : 'Buat link' }}
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      </div>

      <div class="divide-y divide-slate-100 sm:hidden">
        <article v-for="c in customers" :key="c.id" class="space-y-3 p-4">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <h2 class="truncate text-sm font-semibold text-slate-900">{{ c.display_name }}</h2>
              <p class="mt-1 text-xs text-slate-500">
                <span v-if="c.telegram_username">@{{ c.telegram_username }}</span>
                <span v-else>Telegram belum ditautkan</span>
              </p>
            </div>
            <span class="shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="statusBadge(c.status)">
              {{ c.status }}
            </span>
          </div>
          <p v-if="c.internal_notes" class="line-clamp-2 text-xs leading-5 text-slate-500">{{ c.internal_notes }}</p>
          <p class="text-xs text-slate-400">Bergabung {{ formatDate(c.created_at) }}</p>
          <div class="grid grid-cols-2 gap-2">
            <button class="rounded-full border border-[#1c1c1f]/10 px-3 py-2 text-xs font-semibold" @click="openEditCustomer(c)">Edit</button>
            <button class="rounded-full border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700" @click="archiveCustomer(c)">Arsipkan</button>
            <button
              class="col-span-2 rounded-full bg-[#1c1c1f] px-3 py-2 text-xs font-semibold text-white disabled:opacity-40"
              :disabled="creatingLink"
              @click="createTelegramLink(c)"
            >
              {{ c.telegram_user_id ? 'Buat tautan Telegram baru' : 'Tautkan Telegram' }}
            </button>
          </div>
        </article>
      </div>
    </div>

    <!-- Modal: Add Customer -->
    <Teleport to="body">
      <Transition name="bento-overlay">
      <div v-if="showAddCustomer" class="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/35 p-0 backdrop-blur-md sm:items-center sm:p-4" @click.self="showAddCustomer = false">
        <div class="bento-modal max-h-[92dvh] w-full overflow-y-auto rounded-t-[28px] sm:max-h-[calc(100dvh-2rem)] sm:max-w-lg sm:rounded-[28px]">
          <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100">
            <h3 class="font-semibold text-gray-900">{{ editingCustomerId ? 'Edit Customer' : 'Tambah Customer Baru' }}</h3>
            <button @click="showAddCustomer = false" class="text-gray-400 hover:text-gray-600">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <form @submit.prevent="submitCustomer" class="bento-form space-y-4 px-6 py-5">
            <div v-if="customerError" class="bg-red-50 border border-red-200 text-red-600 text-sm rounded-lg px-3 py-2">{{ customerError }}</div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Nama <span class="text-red-500">*</span></label>
              <input v-model="customerForm.display_name" type="text" required placeholder="contoh: Budi Santoso"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Username Telegram</label>
              <div class="relative">
                <span class="absolute left-3 top-2 text-gray-400 text-sm">@</span>
                <input v-model="customerForm.telegram_username" type="text" placeholder="username (opsional)"
                  class="w-full border border-gray-300 rounded-lg pl-7 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Status</label>
              <select v-model="customerForm.status"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <option value="ACTIVE">Active</option>
                <option value="INACTIVE">Inactive</option>
                <option value="SUSPENDED">Suspended</option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Catatan Internal</label>
              <textarea v-model="customerForm.internal_notes" rows="2" placeholder="Opsional"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none" />
            </div>

            <!-- Optional Initial Rental assignment -->
            <div v-if="!editingCustomerId" class="border-t border-gray-100 pt-3">
              <label class="flex items-center gap-2 cursor-pointer">
                <input
                  v-model="customerForm.assign_rental"
                  type="checkbox"
                  class="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
                <span class="text-sm font-medium text-gray-800">Sertakan Rental Produk Pertama</span>
              </label>
              <p class="text-xs text-gray-500 mt-0.5 ml-6">
                Langsung buat data sewa dan relasikan ke produk serta varian yang dipilih
              </p>

              <div v-if="customerForm.assign_rental" class="mt-3 space-y-3 rounded-xl bg-slate-50 p-3.5 border border-slate-200">
                <div>
                  <label class="block text-xs font-semibold text-gray-700 mb-1">
                    Pilih Produk <span class="text-red-500">*</span>
                  </label>
                  <select
                    v-model="customerForm.product_id"
                    @change="onProductChange"
                    required
                    class="w-full border border-gray-300 bg-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="" disabled>-- Pilih Produk --</option>
                    <option v-for="p in products" :key="p.id" :value="p.id">
                      {{ p.name }} ({{ p.category }})
                    </option>
                  </select>
                </div>

                <div>
                  <label class="block text-xs font-semibold text-gray-700 mb-1">
                    Pilih Varian Produk <span class="text-red-500">*</span>
                  </label>
                  <select
                    v-model="customerForm.product_variant_id"
                    @change="onVariantChange"
                    :disabled="!customerForm.product_id"
                    required
                    class="w-full border border-gray-300 bg-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-gray-100 disabled:text-gray-400"
                  >
                    <option value="" disabled>
                      {{ customerForm.product_id ? '-- Pilih Varian --' : '-- Pilih Produk Dahulu --' }}
                    </option>
                    <option v-for="v in availableVariants" :key="v.id" :value="v.id">
                      {{ v.name }} - {{ v.duration_value }} {{ v.duration_unit.toLowerCase() }} ({{ v.currency }} {{ Number(v.default_price).toLocaleString('id-ID') }})
                    </option>
                  </select>
                </div>

                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="block text-xs font-semibold text-gray-700 mb-1">Tanggal Mulai</label>
                    <input
                      v-model="customerForm.start_date"
                      type="date"
                      required
                      class="w-full border border-gray-300 bg-white rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <label class="block text-xs font-semibold text-gray-700 mb-1">Model Perpanjangan</label>
                    <select
                      v-model="customerForm.renewal_model"
                      class="w-full border border-gray-300 bg-white rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    >
                      <option value="CONTINUOUS">Continuous (Nyambung)</option>
                      <option value="IMMEDIATE">Immediate (Saat bayar)</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label class="block text-xs font-semibold text-gray-700 mb-1">Harga Kesepakatan (IDR)</label>
                  <input
                    v-model="customerForm.agreed_price"
                    type="number"
                    min="0"
                    step="1000"
                    placeholder="Sesuai harga varian default"
                    class="w-full border border-gray-300 bg-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>
            </div>

            <div class="flex gap-3 pt-2">
              <button type="button" @click="showAddCustomer = false"
                class="flex-1 border border-gray-300 text-gray-700 text-sm font-medium py-2 rounded-lg hover:bg-gray-50 transition">
                Batal
              </button>
              <button type="submit" :disabled="addingCustomer"
                class="bento-primary flex-1 py-2.5 text-sm font-semibold disabled:opacity-50">
                {{ addingCustomer ? 'Menyimpan...' : 'Simpan' }}
              </button>
            </div>
          </form>
        </div>
      </div>
      </Transition>
    </Teleport>

    <Teleport to="body">
      <Transition name="bento-overlay">
        <div
          v-if="showTelegramLink"
          class="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/35 p-0 backdrop-blur-md sm:items-center sm:p-4"
          @click.self="showTelegramLink = false"
        >
          <div class="bento-modal w-full space-y-4 rounded-t-[28px] p-6 sm:max-w-md sm:rounded-[28px]">
            <div class="flex items-center justify-between">
              <div>
                <p class="text-xs font-semibold uppercase tracking-wider text-[#1c1c1f]/40">Telegram quick access</p>
                <h2 class="mt-1 text-lg font-bold text-[#1c1c1f]">{{ linkCustomerName }}</h2>
              </div>
              <button class="text-xl text-[#1c1c1f]/40" @click="showTelegramLink = false">×</button>
            </div>
            <p class="text-sm leading-6 text-[#1c1c1f]/60">
              Kirim perintah ini ke customer. Tautan hanya dapat digunakan sekali dan akan kedaluwarsa
              {{ formatDate(linkExpiresAt) }}.
            </p>
            <div class="rounded-2xl bg-[#1c1c1f]/[0.04] p-3">
              <code class="block break-all text-sm font-semibold text-[#1c1c1f]">{{ linkCommand }}</code>
            </div>
            <p v-if="linkError" class="text-xs text-[#1c1c1f]/55">{{ linkError }}</p>
            <div class="flex gap-3">
              <button class="bento-white flex-1 py-2.5 text-sm font-semibold" @click="copyTelegramCommand">
                Salin perintah
              </button>
              <button class="bento-primary flex-1 py-2.5 text-sm font-semibold" @click="showTelegramLink = false">
                Selesai
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </AppLayout>
</template>
