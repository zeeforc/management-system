<script setup lang="ts">
import { ref, onMounted } from 'vue'
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
  description: string | null
  category: string
  image_url: string | null
  has_profile_pin: boolean
  status: string
  variants: ProductVariant[]
}

const products = ref<Product[]>([])
const loading = ref(true)
const error = ref('')

// Modal add product
const showAddProduct = ref(false)
const addingProduct = ref(false)
const editingProductId = ref<string | null>(null)
const productForm = ref({
  name: '',
  description: '',
  category: '',
  image_url: '',
  has_profile_pin: false,
  status: 'ACTIVE',
})
const productError = ref('')

// Modal add variant
const showAddVariant = ref(false)
const addingVariant = ref(false)
const selectedProductId = ref('')
const selectedProductName = ref('')
const editingVariantId = ref<string | null>(null)
const variantForm = ref({ name: '', duration_value: 1, duration_unit: 'MONTHS', default_price: '', currency: 'IDR', status: 'ACTIVE' })
const variantError = ref('')

async function fetchProducts() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.get('/products?page=1&page_size=100')
    products.value = res.data.items
  } catch (e: any) {
    error.value = e.response?.data?.detail ?? 'Gagal memuat produk.'
  } finally {
    loading.value = false
  }
}

async function submitProduct() {
  productError.value = ''
  addingProduct.value = true
  try {
    const payload: any = {
      name: productForm.value.name.trim(),
      category: productForm.value.category.trim(),
      has_profile_pin: productForm.value.has_profile_pin,
      status: productForm.value.status,
    }
    if (editingProductId.value) {
      payload.description = productForm.value.description.trim() || null
      payload.image_url = productForm.value.image_url.trim() || null
    } else {
      if (productForm.value.description.trim()) payload.description = productForm.value.description.trim()
      if (productForm.value.image_url.trim()) payload.image_url = productForm.value.image_url.trim()
    }

    if (editingProductId.value) {
      await api.patch(`/products/${editingProductId.value}`, payload)
    } else {
      await api.post('/products', payload)
    }
    showAddProduct.value = false
    editingProductId.value = null
    productForm.value = {
      name: '',
      description: '',
      category: '',
      image_url: '',
      has_profile_pin: false,
      status: 'ACTIVE',
    }
    await fetchProducts()
  } catch (e: any) {
    productError.value = e.response?.data?.detail ?? 'Gagal menambah produk.'
  } finally {
    addingProduct.value = false
  }
}

function openAddProduct() {
  editingProductId.value = null
  productError.value = ''
  productForm.value = {
    name: '',
    description: '',
    category: '',
    image_url: '',
    has_profile_pin: false,
    status: 'ACTIVE',
  }
  showAddProduct.value = true
}

function openEditProduct(product: Product) {
  editingProductId.value = product.id
  productError.value = ''
  productForm.value = {
    name: product.name,
    description: product.description ?? '',
    category: product.category,
    image_url: product.image_url ?? '',
    has_profile_pin: product.has_profile_pin,
    status: product.status,
  }
  showAddProduct.value = true
}

async function archiveProduct(product: Product) {
  if (!window.confirm(`Arsipkan produk "${product.name}"? Riwayat rental akan tetap disimpan.`)) return
  try {
    await api.post(`/products/${product.id}/archive`)
    await fetchProducts()
  } catch (cause: any) {
    error.value = cause.response?.data?.detail ?? 'Gagal mengarsipkan produk.'
  }
}

function openAddVariant(product: Product) {
  editingVariantId.value = null
  selectedProductId.value = product.id
  selectedProductName.value = product.name
  variantForm.value = { name: '', duration_value: 1, duration_unit: 'MONTHS', default_price: '', currency: 'IDR', status: 'ACTIVE' }
  variantError.value = ''
  showAddVariant.value = true
}

function openEditVariant(product: Product, variant: ProductVariant) {
  selectedProductId.value = product.id
  selectedProductName.value = product.name
  editingVariantId.value = variant.id
  variantError.value = ''
  variantForm.value = {
    name: variant.name,
    duration_value: variant.duration_value,
    duration_unit: variant.duration_unit,
    default_price: variant.default_price,
    currency: variant.currency,
    status: variant.status,
  }
  showAddVariant.value = true
}

async function submitVariant() {
  variantError.value = ''
  addingVariant.value = true
  try {
    const payload = {
      name: variantForm.value.name.trim(),
      duration_value: Number(variantForm.value.duration_value),
      duration_unit: variantForm.value.duration_unit,
      default_price: variantForm.value.default_price,
      currency: variantForm.value.currency,
      status: variantForm.value.status,
    }
    if (editingVariantId.value) {
      await api.patch(`/products/variants/${editingVariantId.value}`, payload)
    } else {
      await api.post('/products/variants', {
        product_id: selectedProductId.value,
        ...payload,
      })
    }
    showAddVariant.value = false
    editingVariantId.value = null
    await fetchProducts()
  } catch (e: any) {
    variantError.value = e.response?.data?.detail ?? 'Gagal menambah varian.'
  } finally {
    addingVariant.value = false
  }
}

async function archiveVariant(variant: ProductVariant) {
  if (!window.confirm(`Arsipkan varian "${variant.name}"? Riwayat rental tetap disimpan.`)) return
  try {
    await api.post(`/products/variants/${variant.id}/archive`)
    await fetchProducts()
  } catch (cause: any) {
    error.value = cause.response?.data?.detail ?? 'Gagal mengarsipkan varian.'
  }
}

function statusBadge(status: string) {
  if (status === 'ACTIVE') return 'bg-[#1c1c1f] text-white'
  if (status === 'INACTIVE') return 'bg-[#1c1c1f]/[0.07] text-[#1c1c1f]/55'
  return 'bg-[#1c1c1f]/[0.05] text-[#1c1c1f]/40'
}

onMounted(fetchProducts)
</script>

<template>
  <AppLayout>
    <div class="mb-6 flex animate-fade-up flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="mb-1 text-[11px] font-bold uppercase tracking-[0.2em] text-[#1c1c1f]/35">Katalog</p>
        <h1 class="bento-page-title">Produk & Varian</h1>
        <p class="mt-1 text-sm text-[#1c1c1f]/45">Atur produk, durasi, dan harga rental.</p>
      </div>
      <button
        @click="openAddProduct"
        class="bento-primary inline-flex w-full items-center justify-center gap-2 px-5 py-3 text-sm font-semibold sm:w-auto"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        Tambah Produk
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="space-y-3">
      <div v-for="i in 3" :key="i" class="h-28 animate-pulse rounded-[28px] bg-white/50 p-6">
        <div class="h-4 bg-gray-200 rounded w-1/4 mb-2"></div>
        <div class="h-3 bg-gray-100 rounded w-1/3"></div>
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="bento-white border border-rose-200 p-4 text-sm text-rose-700">{{ error }}</div>

    <!-- Empty -->
    <div v-else-if="products.length === 0" class="bento-glass py-16 text-center text-[#1c1c1f]/45">
      <svg class="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
      <p class="font-medium">Belum ada produk</p>
      <p class="text-sm mt-1">Klik "Tambah Produk" untuk mulai</p>
    </div>

    <!-- Product list -->
    <div v-else class="space-y-4">
      <div
        v-for="product in products"
        :key="product.id"
        class="bento-white animate-fade-up overflow-hidden"
      >
        <!-- Product header -->
        <div class="flex flex-col gap-3 border-b border-[#1c1c1f]/[0.06] px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div>
            <div class="flex items-center gap-2">
              <h2 class="font-semibold text-gray-900">{{ product.name }}</h2>
              <span class="text-xs px-2 py-0.5 rounded-full font-medium" :class="statusBadge(product.status)">
                {{ product.status }}
              </span>
            </div>
            <p class="text-xs text-gray-400 mt-0.5">
              {{ product.category }}<span v-if="product.description"> · {{ product.description }}</span>
              <span v-if="product.has_profile_pin"> · Memerlukan profile & PIN</span>
            </p>
          </div>
          <button
            @click="openAddVariant(product)"
            class="inline-flex w-full items-center justify-center gap-1.5 rounded-full border border-[#1c1c1f]/15 px-4 py-2 text-xs font-semibold text-[#1c1c1f]/70 transition hover:border-[#1c1c1f] hover:bg-[#1c1c1f] hover:text-white sm:w-auto"
          >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            Tambah Varian
          </button>
          <div class="flex gap-2 sm:ml-auto">
            <button class="rounded-full border border-[#1c1c1f]/10 px-3 py-2 text-xs font-semibold" @click="openEditProduct(product)">Edit</button>
            <button class="rounded-full border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700" @click="archiveProduct(product)">Arsipkan</button>
          </div>
        </div>

        <!-- Variants -->
        <div v-if="product.variants.length > 0" class="divide-y divide-[#1c1c1f]/[0.05]">
          <div
            v-for="v in product.variants"
            :key="v.id"
            class="flex flex-col gap-2 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between sm:px-6"
          >
            <div>
              <span class="font-medium text-gray-700">{{ v.name }}</span>
              <span class="text-gray-400 ml-2">{{ v.duration_value }} {{ v.duration_unit.toLowerCase() }}</span>
            </div>
            <div class="flex flex-wrap items-center gap-2 sm:gap-3">
              <span class="text-gray-700 font-medium">{{ v.currency }} {{ Number(v.default_price).toLocaleString('id-ID') }}</span>
              <span class="text-xs px-2 py-0.5 rounded-full" :class="statusBadge(v.status)">{{ v.status }}</span>
              <button class="rounded-full border border-[#1c1c1f]/10 px-3 py-1.5 text-xs font-semibold" @click="openEditVariant(product, v)">Edit</button>
              <button class="rounded-full border border-rose-200 px-3 py-1.5 text-xs font-semibold text-rose-700" @click="archiveVariant(v)">Arsipkan</button>
            </div>
          </div>
        </div>
        <div v-else class="px-4 py-3 text-sm italic text-slate-400 sm:px-6">Belum ada varian</div>
      </div>
    </div>

    <!-- Modal: Add Product -->
    <Teleport to="body">
      <Transition name="bento-overlay">
      <div v-if="showAddProduct" class="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/35 p-0 backdrop-blur-md sm:items-center sm:p-4" @click.self="showAddProduct = false">
        <div class="bento-modal max-h-[92dvh] w-full overflow-y-auto rounded-t-[28px] sm:max-h-[calc(100dvh-2rem)] sm:max-w-md sm:rounded-[28px]">
          <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100">
            <h3 class="font-semibold text-gray-900">{{ editingProductId ? 'Edit Produk' : 'Tambah Produk Baru' }}</h3>
            <button @click="showAddProduct = false" class="text-gray-400 hover:text-gray-600">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <form @submit.prevent="submitProduct" class="bento-form space-y-4 px-6 py-5">
            <div v-if="productError" class="bg-red-50 border border-red-200 text-red-600 text-sm rounded-lg px-3 py-2">{{ productError }}</div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Nama Produk <span class="text-red-500">*</span></label>
              <input v-model="productForm.name" type="text" required placeholder="contoh: Netflix Premium"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Kategori <span class="text-red-500">*</span></label>
              <input v-model="productForm.category" type="text" required placeholder="contoh: Streaming"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Deskripsi</label>
              <textarea v-model="productForm.description" rows="2" placeholder="Opsional"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">URL Gambar</label>
              <input v-model="productForm.image_url" type="url" placeholder="https://... (opsional)"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </div>
            <label class="flex items-start gap-3 rounded-xl border border-gray-200 p-3 text-sm text-gray-700">
              <input
                v-model="productForm.has_profile_pin"
                type="checkbox"
                class="mt-0.5 h-4 w-4 rounded border-gray-300 accent-[#1c1c1f]"
              />
              <span>
                <span class="block font-medium">Produk ini memakai profile dan PIN</span>
                <span class="mt-0.5 block text-xs text-gray-500">
                  Aktifkan agar kolom profile dan PIN muncul saat membuat rental.
                </span>
              </span>
            </label>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Status</label>
              <select v-model="productForm.status"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <option value="ACTIVE">Active</option>
                <option value="INACTIVE">Inactive</option>
              </select>
            </div>

            <div class="flex gap-3 pt-2">
              <button type="button" @click="showAddProduct = false"
                class="flex-1 border border-gray-300 text-gray-700 text-sm font-medium py-2 rounded-lg hover:bg-gray-50 transition">
                Batal
              </button>
              <button type="submit" :disabled="addingProduct"
                class="bento-primary flex-1 py-2.5 text-sm font-semibold disabled:opacity-50">
                {{ addingProduct ? 'Menyimpan...' : 'Simpan' }}
              </button>
            </div>
          </form>
        </div>
      </div>
      </Transition>
    </Teleport>

    <!-- Modal: Add Variant -->
    <Teleport to="body">
      <Transition name="bento-overlay">
      <div v-if="showAddVariant" class="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/35 p-0 backdrop-blur-md sm:items-center sm:p-4" @click.self="showAddVariant = false">
        <div class="bento-modal max-h-[92dvh] w-full overflow-y-auto rounded-t-[28px] sm:max-h-[calc(100dvh-2rem)] sm:max-w-md sm:rounded-[28px]">
          <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100">
            <div>
              <h3 class="font-semibold text-gray-900">{{ editingVariantId ? 'Edit Varian' : 'Tambah Varian' }}</h3>
              <p class="text-xs text-gray-400 mt-0.5">{{ selectedProductName }}</p>
            </div>
            <button @click="showAddVariant = false" class="text-gray-400 hover:text-gray-600">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <form @submit.prevent="submitVariant" class="bento-form space-y-4 px-6 py-5">
            <div v-if="variantError" class="bg-red-50 border border-red-200 text-red-600 text-sm rounded-lg px-3 py-2">{{ variantError }}</div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Nama Varian <span class="text-red-500">*</span></label>
              <input v-model="variantForm.name" type="text" required placeholder="contoh: 1 Bulan"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Durasi <span class="text-red-500">*</span></label>
                <input v-model="variantForm.duration_value" type="number" required min="1"
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Satuan</label>
                <select v-model="variantForm.duration_unit"
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                  <option value="DAYS">Hari</option>
                  <option value="WEEKS">Minggu</option>
                  <option value="MONTHS">Bulan</option>
                  <option value="YEARS">Tahun</option>
                </select>
              </div>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Harga <span class="text-red-500">*</span></label>
                <input v-model="variantForm.default_price" type="number" required min="0" step="1000" placeholder="50000"
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Mata Uang</label>
                <input v-model="variantForm.currency" type="text" maxlength="10"
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Status</label>
              <select v-model="variantForm.status"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <option value="ACTIVE">Active</option>
                <option value="INACTIVE">Inactive</option>
              </select>
            </div>

            <div class="flex gap-3 pt-2">
              <button type="button" @click="showAddVariant = false"
                class="flex-1 border border-gray-300 text-gray-700 text-sm font-medium py-2 rounded-lg hover:bg-gray-50 transition">
                Batal
              </button>
              <button type="submit" :disabled="addingVariant"
                class="bento-primary flex-1 py-2.5 text-sm font-semibold disabled:opacity-50">
                {{ addingVariant ? 'Menyimpan...' : 'Simpan' }}
              </button>
            </div>
          </form>
        </div>
      </div>
      </Transition>
    </Teleport>
  </AppLayout>
</template>
