<template>
  <div v-if="iframeUrl" class="fixed inset-0 h-screen w-screen overflow-hidden">
    <iframe
      :src="iframeSrc"
      class="h-full w-full border-0"
      title="Game"
      sandbox="allow-scripts allow-same-origin"
    />
  </div>
  <div v-else class="fixed inset-0 flex h-screen w-screen items-center justify-center">
    <p class="text-lg text-slate-500">No iframe URL configured</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

// Disable default layout to ensure full page
definePageMeta({
  layout: false
})

const runtimeConfig = useRuntimeConfig()
const iframeUrl = runtimeConfig.public.iframeUrl as string | undefined

const iframeSrc = computed(() => {
  if (!iframeUrl) return undefined

  // Add ngrok skip browser warning for ngrok URLs
  if (iframeUrl.includes('ngrok') || iframeUrl.includes('ngrok.io')) {
    const url = new URL(iframeUrl)
    url.searchParams.set('ngrok-skip-browser-warning', 'true')
    return url.toString()
  }

  return iframeUrl
})
</script>