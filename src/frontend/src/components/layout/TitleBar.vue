<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { isDark } from '@/composables/useTheme.js'

const isMaximized = ref(false)
const isFocused = ref(true)

onMounted(async () => {
  if (window.electronAPI) {
    isMaximized.value = await window.electronAPI.isMaximized()
    window.electronAPI.onMaximizeChange((maximized) => {
      isMaximized.value = maximized
    })
    window.electronAPI.onFocusChange((focused) => {
      isFocused.value = focused
    })
    // 初始化时通知主进程当前主题
    window.electronAPI.themeChange(isDark.value)
  }
})

// 监听主题变化，通知 Electron 主进程更新窗口背景色
watch(isDark, (val) => {
  if (window.electronAPI) {
    window.electronAPI.themeChange(val)
  }
})

function handleMinimize() {
  window.electronAPI?.minimize()
}

function handleMaximize() {
  window.electronAPI?.maximize()
}

function handleClose() {
  window.electronAPI?.close()
}
</script>

<template>
  <div class="title-bar" :class="{ 'is-unfocused': !isFocused, 'is-dark': isDark, 'is-light': !isDark }">
    <!-- Drag region covers the entire bar -->
    <div class="title-bar-drag-region"></div>

    <!-- Left: App icon + title -->
    <div class="title-bar-left">
      <router-link to="/" class="title-bar-logo" @click.prevent>
        <img src="@/assets/logo.png" alt="logo" class="title-bar-logo-img" />
      </router-link>
      <span class="title-bar-title">MCPackLocalizer</span>
    </div>

    <!-- Right: Window controls (Win11 style) -->
    <div class="title-bar-controls">
      <button
        class="title-bar-btn title-bar-btn-minimize"
        title="最小化"
        @click="handleMinimize"
      >
        <svg width="10" height="1" viewBox="0 0 10 1" fill="none">
          <path d="M0 0.5H10" stroke="currentColor" stroke-width="1" />
        </svg>
      </button>
      <button
        class="title-bar-btn title-bar-btn-maximize"
        :title="isMaximized ? '还原' : '最大化'"
        @click="handleMaximize"
      >
        <!-- Maximize icon (single square) -->
        <svg v-if="!isMaximized" width="10" height="10" viewBox="0 0 10 10" fill="none">
          <path d="M0.5 0.5H9.5V9.5H0.5V0.5Z" stroke="currentColor" stroke-width="1" />
        </svg>
        <!-- Restore icon (overlapping squares) -->
        <svg v-else width="10" height="10" viewBox="0 0 10 10" fill="none">
          <path d="M2.5 0.5H9.5V7.5H2.5V0.5Z" stroke="currentColor" stroke-width="1" />
          <path d="M0.5 2.5H7.5V9.5H0.5V2.5Z" stroke="currentColor" stroke-width="1" fill="var(--titlebar-bg)" />
          <path d="M0.5 2.5H7.5V9.5H0.5V2.5Z" stroke="currentColor" stroke-width="1" />
        </svg>
      </button>
      <button
        class="title-bar-btn title-bar-btn-close"
        title="关闭"
        @click="handleClose"
      >
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
          <path d="M0.5 0.5L9.5 9.5M9.5 0.5L0.5 9.5" stroke="currentColor" stroke-width="1" />
        </svg>
      </button>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.title-bar {
  --titlebar-bg: #0f172a;
  --titlebar-text-color: rgba(255, 255, 255, 0.85);
  --titlebar-height: 32px;
  --titlebar-btn-width: 46px;
  --titlebar-btn-icon-color: rgba(255, 255, 255, 0.85);
  --titlebar-btn-icon-color-hover: #ffffff;
  --titlebar-btn-close-bg-hover: #c42b1c;
  --titlebar-btn-close-icon-hover: #ffffff;

  position: relative;
  height: var(--titlebar-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--titlebar-bg);
  flex-shrink: 0;
  user-select: none;
  -webkit-app-region: drag;
  font-family: $font-family-sans;
  z-index: 9999;
  transition: background-color 0.2s ease;

  // 浅色主题
  &.is-light {
    --titlebar-bg: #f5f7fb;
    --titlebar-text-color: rgba(15, 23, 42, 0.85);
    --titlebar-btn-icon-color: rgba(15, 23, 42, 0.7);
    --titlebar-btn-icon-color-hover: rgba(15, 23, 42, 0.9);
    --titlebar-btn-close-bg-hover: #c42b1c;
    --titlebar-btn-close-icon-hover: #ffffff;

    &.is-unfocused {
      --titlebar-bg: #eef2f7;
      --titlebar-btn-icon-color: rgba(15, 23, 42, 0.35);
      --titlebar-text-color: rgba(15, 23, 42, 0.45);
    }
  }

  // 深色主题
  &.is-dark {
    --titlebar-bg: #0f172a;
    --titlebar-text-color: rgba(255, 255, 255, 0.85);
    --titlebar-btn-icon-color: rgba(255, 255, 255, 0.85);
    --titlebar-btn-icon-color-hover: #ffffff;
    --titlebar-btn-close-bg-hover: #c42b1c;
    --titlebar-btn-close-icon-hover: #ffffff;

    &.is-unfocused {
      --titlebar-bg: #1e293b;
      --titlebar-btn-icon-color: rgba(255, 255, 255, 0.45);
      --titlebar-text-color: rgba(255, 255, 255, 0.45);
    }
  }
}

.title-bar-drag-region {
  position: absolute;
  inset: 0;
}

.title-bar-left {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 100%;
  padding-left: 12px;
  -webkit-app-region: no-drag;
}

.title-bar-logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  text-decoration: none;
  border-radius: 2px;
  transition: background 0.15s ease;

  .is-dark & {
    &:hover {
      background: rgba(255, 255, 255, 0.08);
    }
  }

  .is-light & {
    &:hover {
      background: rgba(0, 0, 0, 0.06);
    }
  }
}

.title-bar-logo-img {
  width: 14px;
  height: 14px;
  object-fit: contain;
}

.title-bar-title {
  font-size: 12px;
  font-weight: 400;
  color: var(--titlebar-text-color);
  letter-spacing: 0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.title-bar-controls {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: stretch;
  height: 100%;
  -webkit-app-region: no-drag;
}

.title-bar-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--titlebar-btn-width);
  height: 100%;
  border: none;
  outline: none;
  background: transparent;
  color: var(--titlebar-btn-icon-color);
  cursor: pointer;
  padding: 0;
  margin: 0;
  transition: background-color 0.1s ease, color 0.1s ease;
  -webkit-app-region: no-drag;

  svg {
    display: block;
    flex-shrink: 0;
  }

  &:hover {
    background: rgba(255, 255, 255, 0.08);
    color: var(--titlebar-btn-icon-color-hover);

    .is-light & {
      background: rgba(0, 0, 0, 0.06);
    }
  }

  &:active {
    background: rgba(255, 255, 255, 0.04);

    .is-light & {
      background: rgba(0, 0, 0, 0.03);
    }
  }

  &:focus-visible {
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.4);

    .is-light & {
      box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.2);
    }
  }
}

.title-bar-btn-close {
  &:hover {
    background: var(--titlebar-btn-close-bg-hover);
    color: var(--titlebar-btn-close-icon-hover);
  }

  &:active {
    background: #b4271a;
    color: var(--titlebar-btn-close-icon-hover);
  }
}
</style>
