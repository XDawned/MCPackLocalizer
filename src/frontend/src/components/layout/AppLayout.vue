<script setup>
import { computed, provide, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElBreadcrumb, ElBreadcrumbItem } from 'element-plus'
import TitleBar from './TitleBar.vue'
import AppSidebar from './AppSidebar.vue'
import SettingsView from '@/views/SettingsView.vue'
import { getPageMetaByPath, isWorkflowPath } from '@/stores/workflow'

const route = useRoute()

const settingsDialogVisible = ref(false)
const settingsInitialTab = ref('ai')

function openSettings(tab = 'ai') {
  settingsInitialTab.value = tab
  settingsDialogVisible.value = true
}

provide('openSettings', openSettings)

const currentPageMeta = computed(() => getPageMetaByPath(route.path))
const isWorkflowStep = computed(() => isWorkflowPath(route.path))
const hasTaskId = computed(() => !!route.query.taskId)

const breadcrumbItems = computed(() => {
  const path = route.path
  const items = [{ name: '首页', path: '/' }]

  if (path === '/') return items

  if (path.startsWith('/modpack/')) {
    items.push({ name: '检索整合包', path: '/search' })
    items.push({ name: '整合包详情', path })
  } else if (path.startsWith('/settings/')) {
    items.push({ name: '系统设置', path: '/settings' })
    const name = currentPageMeta.value?.label || route.meta?.title || path
    items.push({ name, path })
  } else if (isWorkflowStep.value && hasTaskId.value) {
    items.push({ name: '工作流', path: '/workflow' })
    const name = currentPageMeta.value?.label || route.meta?.title || path
    items.push({ name, path })
  } else {
    const name = currentPageMeta.value?.label || route.meta?.title || path
    items.push({ name, path })
  }

  return items
})

const currentPageTitle = computed(() => {
  if (route.path === '/') return '工作台'
  if (route.path.startsWith('/modpack/')) return '整合包详情'
  return currentPageMeta.value?.label || route.meta?.title || 'MCPackLocalizer'
})

const currentPageDescription = computed(() => {
  if (route.path === '/') return '从统一桌面工作区开始本地化任务。'
  if (route.path === '/search') return '检索来源、调整筛选条件并启动后续工作流。'
  if (route.path.startsWith('/settings')) return '管理提供商、主题和缓存等桌面运行配置。'
  if (isWorkflowStep.value) return '按步骤推进当前整合包本地化流程。'
  return '保持命令区稳定、层级清晰的桌面工具体验。'
})

const showBreadcrumb = computed(() => breadcrumbItems.value.length > 1)
</script>

<template>
  <div class="app-shell">
    <TitleBar />
    <div class="app-body">
      <AppSidebar />
      <div class="app-workspace">
        <header class="workspace-header">
          <div class="workspace-header-main">
            <div v-if="showBreadcrumb" class="workspace-breadcrumb">
              <ElBreadcrumb>
                <ElBreadcrumbItem
                  v-for="(item, index) in breadcrumbItems"
                  :key="item.path"
                  :to="index < breadcrumbItems.length - 1 ? item.path : undefined"
                >
                  {{ item.name }}
                </ElBreadcrumbItem>
              </ElBreadcrumb>
            </div>
          </div>
        </header>

        <div class="workspace-content">
          <router-view v-slot="{ Component }">
            <transition name="page-fade" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
        </div>
      </div>
    </div>

    <SettingsView
      v-if="settingsDialogVisible"
      dialog-mode
      :initial-tab="settingsInitialTab"
      @update:dialog-visible="settingsDialogVisible = $event"
    />
  </div>
</template>

<style lang="scss" scoped>
.app-shell {
  width: 100%;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--notion-canvas);
}

.app-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

.app-workspace {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.2), transparent 160px),
    var(--notion-surface-soft);
}

.workspace-header {
  position: relative;
  z-index: 1;
  flex-shrink: 0;
  padding: $spacing-sm $spacing-sm $spacing-xs;
  border-bottom: 1px solid var(--notion-hairline-soft);
  background: var(--fluent-surface-2);
  backdrop-filter: blur(18px);
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.14);
}

.workspace-header-main {
  display: flex;
  flex-direction: column;
  gap: $spacing-sm;
}

.workspace-breadcrumb {
  :deep(.el-breadcrumb) {
    font-size: var(--notion-font-size-caption);
    font-family: var(--notion-font-sans);
    line-height: 1.6;
  }

  :deep(.el-breadcrumb__inner) {
    color: var(--notion-steel);
    font-weight: $font-weight-regular;
    transition: color $transition-fast;

    &.is-link:hover {
      color: var(--fluent-accent);
    }
  }

  :deep(.el-breadcrumb__item:last-child .el-breadcrumb__inner) {
    color: var(--notion-ink);
    font-weight: $font-weight-medium;
    cursor: default;
  }

  :deep(.el-breadcrumb__separator) {
    color: var(--notion-muted);
    margin: 0 $spacing-xxs;
  }
}

.workspace-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity $transition-normal, transform $transition-normal;
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-3px);
}
</style>
