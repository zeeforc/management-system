<script setup lang="ts">
import { useRegisterSW } from 'virtual:pwa-register/vue'
import { onMounted, onUnmounted, ref } from 'vue'

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

const { needRefresh, updateServiceWorker } = useRegisterSW()
const installPrompt = ref<InstallPromptEvent | null>(null)
const installError = ref('')
const isIos = /iphone|ipad|ipod/i.test(navigator.userAgent)
const isStandalone = ref(
  window.matchMedia('(display-mode: standalone)').matches ||
    ('standalone' in window.navigator && window.navigator.standalone === true),
)

function captureInstallPrompt(event: Event) {
  event.preventDefault()
  installPrompt.value = event as InstallPromptEvent
}

function markInstalled() {
  isStandalone.value = true
  installPrompt.value = null
}

async function installApp() {
  if (!installPrompt.value) return
  installError.value = ''

  try {
    const prompt = installPrompt.value
    await prompt.prompt()
    const choice = await prompt.userChoice
    if (choice.outcome === 'accepted') installPrompt.value = null
  } catch {
    installError.value = 'Instalasi belum berhasil. Coba lagi dari menu browser.'
  }
}

onMounted(() => {
  window.addEventListener('beforeinstallprompt', captureInstallPrompt)
  window.addEventListener('appinstalled', markInstalled)
})

onUnmounted(() => {
  window.removeEventListener('beforeinstallprompt', captureInstallPrompt)
  window.removeEventListener('appinstalled', markInstalled)
})
</script>

<template>
  <aside
    v-if="needRefresh || (!isStandalone && (installPrompt || isIos))"
    class="fixed bottom-4 left-4 right-4 z-50 mx-auto flex max-w-md items-center justify-between gap-4 rounded-2xl bg-[#1c1c1f] px-5 py-4 text-white shadow-2xl"
    aria-live="polite"
  >
    <div class="min-w-0">
      <p class="text-sm font-semibold">
        {{ needRefresh ? 'Pembaruan aplikasi tersedia' : 'Pasang Rental Management' }}
      </p>
      <p v-if="needRefresh" class="mt-1 text-xs text-white/70">
        Muat ulang untuk menggunakan versi terbaru.
      </p>
      <p v-else-if="isIos && !installPrompt" class="mt-1 text-xs text-white/70">
        Buka menu Bagikan Safari, lalu pilih “Tambahkan ke Layar Utama”.
      </p>
      <p v-if="installError" class="mt-1 text-xs text-rose-200">{{ installError }}</p>
    </div>

    <button
      v-if="needRefresh"
      type="button"
      class="shrink-0 rounded-full bg-white px-4 py-2 text-xs font-semibold text-[#1c1c1f]"
      @click="updateServiceWorker(true)"
    >
      Perbarui
    </button>
    <button
      v-else-if="installPrompt"
      type="button"
      class="shrink-0 rounded-full bg-white px-4 py-2 text-xs font-semibold text-[#1c1c1f]"
      @click="installApp"
    >
      Install
    </button>
  </aside>
</template>
