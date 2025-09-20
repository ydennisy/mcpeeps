<template>
  <UApp>
    <div class="flex min-h-screen flex-col bg-slate-100/80 text-slate-800">
      <header class="border-b border-slate-200/70 bg-white/90 backdrop-blur supports-[backdrop-filter]:bg-white/70">
        <UContainer class="flex flex-col gap-4 py-6 sm:flex-row sm:items-center sm:justify-between">
          <div class="flex items-center gap-3">
            <div class="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary-100 text-2xl">
              🤖
            </div>
            <div>
              <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">MCPeeps</p>
              <h1 class="text-xl font-semibold text-slate-900">The Boardroom</h1>
              <p class="text-sm text-slate-500">Organize your agents with a A2A</p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <UBadge color="primary" variant="soft">Live status ✨</UBadge>
            <UBadge color="gray" variant="soft">Friendly vibes 🌈</UBadge>
          </div>
        </UContainer>
      </header>
      <main class="flex-1">
        <UContainer class="py-10">
          <slot />
        </UContainer>
      </main>
      <footer class="border-t border-slate-200/70 bg-white/80">
        <UContainer class="flex flex-col gap-2 py-6 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between">
          <span>Built with care by the MCPeeps crew 🧠💫</span>
          <span>Keep exploring &amp; have fun! 🪄</span>
        </UContainer>
      </footer>
    </div>
  </UApp>
</template>
