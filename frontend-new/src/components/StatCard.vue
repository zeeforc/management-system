<script setup lang="ts">
defineProps<{
  label: string
  value: number
  color: string
  icon: string
}>()
</script>

<template>
  <div class="bento-glass p-5 animate-fade-up">
    <div class="flex items-start justify-between">
      <p class="text-[13px] text-[#1c1c1f]/50 font-semibold tracking-wide uppercase">{{ label }}</p>
      <span class="p-2.5 rounded-2xl bg-[#1c1c1f]/5">
        <svg class="w-4 h-4 text-[#1c1c1f]/40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icon" />
        </svg>
      </span>
    </div>
    <p class="text-3xl font-extrabold text-[#1c1c1f] mt-3 tracking-tight">{{ value }}</p>
  </div>
</template>
