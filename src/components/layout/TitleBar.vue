/**
 * 标题栏组件
 */
<template>
  <div class="title-bar">
    <div class="title-bar-drag-region">
      <div class="title-bar-icon">
        <img src="@/assets/images/logo.png" alt="Logo" />
      </div>
      <span class="title-bar-title">整合包本地化工具</span>
    </div>
    <div class="title-bar-controls">
      <fluent-button appearance="stealth" class="control-button" @click="handleMinimize">
        <svg width="10" height="1" viewBox="0 0 10 1">
          <rect width="10" height="1" fill="currentColor" />
        </svg>
      </fluent-button>
      <fluent-button appearance="stealth" class="control-button" @click="handleMaximize">
        <svg width="10" height="10" viewBox="0 0 10 10">
          <rect width="10" height="10" fill="none" stroke="currentColor" stroke-width="1" />
        </svg>
      </fluent-button>
      <fluent-button appearance="stealth" class="control-button close-button" @click="handleClose">
        <svg width="10" height="10" viewBox="0 0 10 10">
          <path d="M0,0 L10,10 M10,0 L0,10" stroke="currentColor" stroke-width="1" />
        </svg>
      </fluent-button>
    </div>
  </div>
</template>

<script setup>
const handleMinimize = async () => {
  if (window.electronAPI) {
    await window.electronAPI.window.minimize()
  }
}

const handleMaximize = async () => {
  if (window.electronAPI) {
    await window.electronAPI.window.maximize()
  }
}

const handleClose = async () => {
  if (window.electronAPI) {
    await window.electronAPI.window.close()
  }
}
</script>

<style scoped>
.title-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: var(--title-bar-height);
  background-color: var(--surface-color);
  border-bottom: 1px solid var(--border-color);
  user-select: none;
  -webkit-app-region: drag;
}

.title-bar-drag-region {
  display: flex;
  align-items: center;
  height: 100%;
  padding-left: 8px;
}

.title-bar-icon {
  display: flex;
  align-items: center;
  margin-right: 8px;
}

.title-bar-icon img {
  width: 16px;
  height: 16px;
}

.title-bar-title {
  font-size: 12px;
  color: var(--text-color);
}

.title-bar-controls {
  display: flex;
  -webkit-app-region: no-drag;
}

.control-button {
  width: 46px;
  height: var(--title-bar-height);
  border-radius: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.control-button:hover {
  background-color: var(--hover-color);
}

.control-button.close-button:hover {
  background-color: var(--error-color);
  color: white;
}
</style>