<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(email.value, password.value)
    router.push({ name: 'dashboard' })
  } catch (e: any) {
    error.value =
      e.response?.data?.detail ?? 'Login gagal. Periksa email & password.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center p-4 sm:p-6">
    <div class="w-full max-w-md animate-fade-up">
      <!-- Logo / Title -->
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center w-14 h-14 bg-[#1c1c1f] rounded-[22px] mb-4 shadow-lg shadow-black/10">
          <svg class="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"
              d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5v-9Z M4.5 7.8 12 12l7.5-4.2M12 12v8.5" />
          </svg>
        </div>
        <h1 class="text-2xl font-extrabold text-[#1c1c1f] tracking-tight">Rental Management</h1>
        <p class="text-[#1c1c1f]/40 mt-1.5 text-sm font-medium">Masuk ke sistem monitoring rental</p>
      </div>

      <!-- Card -->
      <div class="bento-glass p-8" style="border-radius: 28px;">
        <form @submit.prevent="handleLogin" class="space-y-5">
          <!-- Error alert -->
          <div v-if="error" class="flex items-start gap-3 bg-red-50/80 border border-red-200/60 text-red-700 rounded-2xl px-4 py-3 text-sm backdrop-blur">
            <svg class="w-4 h-4 mt-0.5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                clip-rule="evenodd" />
            </svg>
            {{ error }}
          </div>

          <!-- Email -->
          <div>
            <label for="email" class="block text-sm font-semibold text-[#1c1c1f]/70 mb-1.5">
              Email
            </label>
            <input
              id="email"
              v-model="email"
              type="email"
              autocomplete="email"
              required
              placeholder="owner@example.com"
              class="w-full px-4 py-3 rounded-2xl border border-[#1c1c1f]/10 bg-white/70 text-sm text-[#1c1c1f] placeholder-[#1c1c1f]/25 focus:outline-none focus:ring-2 focus:ring-[#1c1c1f]/20 focus:border-transparent transition backdrop-blur"
            />
          </div>

          <!-- Password -->
          <div>
            <label for="password" class="block text-sm font-semibold text-[#1c1c1f]/70 mb-1.5">
              Password
            </label>
            <input
              id="password"
              v-model="password"
              type="password"
              autocomplete="current-password"
              required
              placeholder="••••••••"
              class="w-full px-4 py-3 rounded-2xl border border-[#1c1c1f]/10 bg-white/70 text-sm text-[#1c1c1f] placeholder-[#1c1c1f]/25 focus:outline-none focus:ring-2 focus:ring-[#1c1c1f]/20 focus:border-transparent transition backdrop-blur"
            />
          </div>

          <!-- Submit -->
          <button
            type="submit"
            :disabled="loading"
            class="w-full bg-[#1c1c1f] hover:bg-[#2a2a2e] disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold text-sm py-3 px-4 rounded-2xl transition-all duration-200 flex items-center justify-center gap-2 shadow-lg shadow-black/10 hover:shadow-xl hover:shadow-black/15"
          >
            <svg v-if="loading" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ loading ? 'Memproses...' : 'Masuk' }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
