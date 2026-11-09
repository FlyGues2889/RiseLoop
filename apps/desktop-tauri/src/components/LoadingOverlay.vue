<script setup>
defineProps({
  label: { type: String, default: "" },
  fullscreen: { type: Boolean, default: false },
});
</script>

<template>
  <div class="loading-overlay" :class="{ fullscreen }" role="status" aria-live="polite" aria-busy="true">
    <div class="loading-content">
      <m3e-loading-indicator variant="contained"></m3e-loading-indicator>
      <span v-if="label" class="label">{{ label }}</span>
    </div>
  </div>
</template>

<style scoped>
.loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  overflow: hidden;
  contain: layout paint;
  max-width: 100%;
  max-height: 100%;
  border-radius: inherit;
  background: var(--md-sys-color-surface);
}

.loading-overlay.fullscreen {
  position: fixed;
  z-index: 100;
  width: 100vw;
  height: 100vh;
}

.loading-content {
  display: grid;
  justify-items: center;
  gap: 0.75rem;
}

.label {
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.75rem;
  letter-spacing: 0.02em;
}
</style>
