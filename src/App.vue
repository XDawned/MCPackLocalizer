/**
 * 根组件
 */
<template>
  <div id="app" :data-theme="theme">
    <TitleBar v-if="!isFullscreen" />
    <MainLayout />
  </div>
</template>

<script setup>
import { ref, onMounted, provide, watch } from 'vue'
import { useTheme } from './composables/useTheme'
import TitleBar from './components/layout/TitleBar.vue'
import MainLayout from './components/layout/MainLayout.vue'

const { theme, toggleTheme } = useTheme()
const isFullscreen = ref(false)

// 提供全局状态
provide('theme', { theme, toggleTheme })
provide('fullscreen', { isFullscreen })

// 监听主题变化
watch(theme, (newTheme) => {
  document.body.setAttribute('data-theme', newTheme)
})

onMounted(() => {
  // 初始化主题
  document.body.setAttribute('data-theme', theme.value)
})
</script>

<style>
/* 全局样式 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

:root {
  /* Fluent UI 颜色变量 */
  --primary-color: #0078d4;
  --background-color: #f3f3f3;
  --surface-color: #ffffff;
  --text-color: #323130;
  --text-secondary-color: #605e5c;
  --border-color: #e1dfdd;
  --hover-color: #f0f0f0;
  --error-color: #a80000;
  --success-color: #107c10;
  --warning-color: #797775;
  
  /* 尺寸变量 */
  --title-bar-height: 32px;
  --navigation-width: 200px;
}

[data-theme="dark"] {
  --background-color: #1b1b1b;
  --surface-color: #2d2d2d;
  --text-color: #ffffff;
  --text-secondary-color: #a0a0a0;
  --border-color: #3d3d3d;
  --hover-color: #3a3a3a;
}

html, body {
  width: 100%;
  height: 100%;
  overflow: hidden;
  font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
  font-size: 14px;
  background-color: var(--background-color);
  color: var(--text-color);
}

#app {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* 滚动条样式 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: var(--background-color);
}

::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary-color);
}

/* Fluent UI 组件样式覆盖 */
fluent-button {
  --accent-fill-rest: var(--primary-color);
}

fluent-text-field {
  --background-color: var(--surface-color);
  --text-color: var(--text-color);
}
</style>