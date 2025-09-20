import { defineNuxtConfig } from 'nuxt/config'

export default defineNuxtConfig({
  modules: ['@nuxt/ui'],
  devtools: { enabled: true },
  runtimeConfig: {
    public: {
      apiBase: 'http://localhost:8000'
    }
  },
  app: {
    head: {
      title: 'The Boardroom'
    }
  },
  css: ['~/assets/css/main.css'],
})
