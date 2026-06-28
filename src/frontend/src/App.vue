<script setup>
import { onMounted } from 'vue'
import AppLayout from '@/components/layout/AppLayout.vue'

onMounted(() => {
  document.documentElement.classList.add('app-loaded')
})
</script>

<template>
  <transition name="app-fade">
    <AppLayout />
  </transition>
</template>

<style lang="scss">
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body, #app {
  height: 100%;
  overflow: hidden;
  font-family: var(--notion-font-sans);
}

#app {
  display: flex;
  flex-direction: column;
  background: var(--notion-canvas);
  color: var(--notion-ink);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
</style>
