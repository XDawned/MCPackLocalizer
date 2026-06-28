<script setup>
import { computed, inject, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { isDark, toggleDark } from '@/composables/useTheme.js'
import {
  GLOBAL_NAV_ITEMS,
  WORKFLOW_STEPS,
  resolveWorkflowStepByPath,
  useWorkflowStore
} from '@/stores/workflow'

const openSettings = inject('openSettings', null)
const route = useRoute()
const router = useRouter()
const workflowStore = useWorkflowStore()

const isCollapsed = ref(false)

const globalNavigation = GLOBAL_NAV_ITEMS
const workflowSteps = WORKFLOW_STEPS

const currentStep = computed(() => workflowStore.currentStep)
const currentStepInfo = computed(() => workflowStore.currentStepInfo)
const workflowStateLabel = computed(() => workflowStore.workflowStateLabel)
const workflowSectionLabel = computed(() => {
  return workflowStore.hasPackContext || workflowStore.hasTaskContext ? '当前任务' : '任务导航'
})
const showTaskNavigation = computed(() => {
  return Boolean(
    workflowStore.hasPackContext ||
    workflowStore.hasTaskContext ||
    resolveWorkflowStepByPath(route.path)
  )
})
const showTaskSummary = computed(() => {
  return Boolean(workflowStore.hasPackContext || workflowStore.hasTaskContext)
})
const canGoBack = computed(() => {
  return showTaskNavigation.value && Boolean(workflowStore.resolvePreviousStep())
})
const primaryProgressPercent = computed(() => {
  const completedCount = workflowSteps.filter(step => stepStatus(step.id) === 'completed').length
  return Math.round((completedCount / workflowSteps.length) * 100)
})

function navGlyph(key) {
  const glyphMap = {
    home: '首',
    search: '检',
    localImport: '导',
    history: '历',
    glossary: '术'
  }
  return glyphMap[key] || '•'
}

function isGlobalItemActive(item) {
  if (item.route === '/search') {
    return route.path === '/search' || route.path.startsWith('/modpack/')
  }
  return route.path === item.route
}

function navigateToGlobal(item) {
  router.push(item.route)
}

function stepStatus(stepId) {
  return workflowStore.stepStatuses[stepId] || 'blocked'
}

function isStepClickable(stepId) {
  return workflowStore.isStepAccessible(stepId) && stepStatus(stepId) !== 'blocked'
}

function handleStepClick(stepId) {
  if (!isStepClickable(stepId)) return
  const location = workflowStore.goToStep(stepId)
  if (location) {
    router.push(location)
  }
}

function handleBack() {
  const location = workflowStore.getBackLocation()
  if (location) {
    router.push(location)
  }
}

function lineClass(stepId) {
  const nextId = stepId + 1
  if (nextId > workflowSteps.length) return 'line-pending'

  const currentStatus = stepStatus(stepId)
  const nextStatus = stepStatus(nextId)

  if (currentStatus === 'completed' && nextStatus === 'completed') return 'line-completed'
  if (currentStatus === 'completed' && ['active', 'pending'].includes(nextStatus)) return 'line-active'
  if (currentStatus === 'active') return 'line-active'
  return 'line-pending'
}

function circleClass(stepId) {
  const status = stepStatus(stepId)
  if (status === 'active') return 'circle-active'
  if (status === 'completed') return 'circle-completed'
  if (status === 'failed') return 'circle-failed'
  if (status === 'blocked') return 'circle-blocked'
  return 'circle-pending'
}

function rowClass(stepId) {
  const classes = []
  if (currentStep.value === stepId) classes.push('step-current')
  if (stepStatus(stepId) === 'completed') classes.push('step-completed')
  if (!isStepClickable(stepId)) classes.push('step-blocked')
  return classes
}

function navRowClass(item) {
  const classes = ['step-row--nav']
  if (isGlobalItemActive(item)) {
    classes.push('step-current')
  }
  return classes
}

const icons = {
  check: 'M9 16.17L4.83 12L3.41 13.41L9 19L21 7L19.59 5.59L9 16.17Z',
  close: 'M18 6L6 18M6 6l12 12',
  chevron: 'M15.41 7.41L14 6L8 12L14 18L15.41 16.59L10.83 12L15.41 7.41Z',
  sun: 'M12 7C9.24 7 7 9.24 7 12C7 14.76 9.24 17 12 17C14.76 17 17 14.76 17 12C17 9.24 14.76 7 12 7ZM12 15C10.34 15 9 13.66 9 12C9 10.34 10.34 9 12 9C13.66 9 15 10.34 15 12C15 13.66 13.66 15 12 15ZM11 2V4H13V2H11ZM11 20V22H13V20H11ZM2 11H4V13H2V11ZM20 11H22V13H20V11ZM4.93 17.66L6.34 19.07L7.76 17.66L6.34 16.24L4.93 17.66ZM16.24 6.34L17.66 4.93L19.07 6.34L17.66 7.76L16.24 6.34ZM4.93 6.34L6.34 4.93L7.76 6.34L6.34 7.76L4.93 6.34ZM16.24 17.66L17.66 19.07L19.07 17.66L17.66 16.24L16.24 17.66Z',
  moon: 'M12.43 2.3C9.53 2.3 6.64 3.35 4.31 5.46C1.98 7.57 0.79 10.28 0.97 13.1C1.15 15.92 2.67 18.55 5.18 20.27C7.69 21.99 10.95 22.63 14.06 22.07C17.17 21.5 19.83 19.77 21.44 17.24L19.66 19.02C18.76 19.92 17.54 20.37 16.31 20.27C15.08 20.17 13.95 19.52 13.17 18.47C12.39 17.43 12.02 16.05 12.15 14.69C12.28 13.32 12.89 12.08 13.87 11.18C14.84 10.28 16.1 9.78 17.42 9.78C18.74 9.78 20 10.26 20.97 11.14L19.19 9.32C18.59 8.72 18.24 7.93 18.19 7.1C18.14 6.27 18.39 5.44 18.91 4.75C19.43 4.06 20.17 3.57 21.02 3.35C19.38 2.67 17.61 2.36 15.84 2.35L14.58 2.32C13.84 2.3 13.12 2.3 12.43 2.3Z',
  gear: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94L14.4 2.81a.48.48 0 0 0-.41-.3h-3.98a.5.5 0 0 0-.44.3l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 0 0-.59.22L2.69 8.87a.49.49 0 0 0 .12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.17.2.3.41.3h3.98c.21 0 .36-.13.41-.3l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 8c2.21 0 4 1.79 4 4s-1.79 4-4 4-4-1.79-4-4 1.79-4 4-4z'
}
</script>

<template>
  <aside class="app-sidebar" :class="{ collapsed: isCollapsed }">
    <div class="sidebar-header">
      <div class="sidebar-logo">
        <div class="sidebar-logo-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" class="sidebar-logo-icon">
            <path
              d="M12 2L2 7v10l10 5 10-5V7L12 2z"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
            />
            <circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.5" />
          </svg>
        </div>
        <div v-show="!isCollapsed" class="sidebar-logo-copy">
          <span class="sidebar-logo-text">MCPackLocalizer</span>
          <span class="sidebar-logo-caption">MC整合包本地化工具</span>
        </div>
      </div>
    </div>

    <div class="sidebar-workflow">
      <section class="sidebar-nav-section">
        <div v-show="!isCollapsed" class="sidebar-section-label">全局导航</div>

        <div
          v-for="item in globalNavigation"
          :key="item.key"
          class="step-row"
          :class="navRowClass(item)"
          @click="navigateToGlobal(item)"
        >
          <div class="step-indicator">
            <div class="step-circle" :class="isGlobalItemActive(item) ? 'circle-active' : 'circle-pending'">
              <span class="step-number">{{ navGlyph(item.key) }}</span>
            </div>
          </div>
          <div v-show="!isCollapsed" class="step-content">
            <span class="step-label">{{ item.label }}</span>
            <span class="step-desc">{{ item.description }}</span>
          </div>
        </div>
      </section>

      <div class="branch-section">
        <div class="branch-section-line"></div>
      </div>

      <section class="sidebar-nav-section">
        <div v-show="!isCollapsed" class="sidebar-section-label">{{ workflowSectionLabel }}</div>

        <div v-if="showTaskSummary && !isCollapsed" class="task-summary-card">
          <div class="task-summary-title-row">
            <span class="task-summary-title">{{ currentStepInfo.label }}</span>
            <span class="task-summary-progress">{{ primaryProgressPercent }}%</span>
          </div>
          <span class="task-summary-desc">{{ workflowStateLabel }}</span>
        </div>

        <button
          v-if="canGoBack"
          class="sidebar-inline-action"
          :class="{ 'sidebar-inline-action--collapsed': isCollapsed }"
          @click="handleBack"
        >
          <svg viewBox="0 0 24 24" class="sidebar-svg collapse-icon">
            <path :d="icons.chevron" />
          </svg>
          <span v-show="!isCollapsed">返回上一步</span>
        </button>

        <template v-if="showTaskNavigation">
          <template v-for="step in workflowSteps" :key="step.id">
            <div
              class="step-row"
              :class="rowClass(step.id)"
              @click="handleStepClick(step.id)"
            >
              <div class="step-indicator">
                <div class="step-circle" :class="circleClass(step.id)">
                  <svg
                    v-if="stepStatus(step.id) === 'completed'"
                    viewBox="0 0 24 24"
                    class="step-icon step-icon-check"
                  >
                    <path :d="icons.check" />
                  </svg>
                  <div v-else-if="stepStatus(step.id) === 'active'" class="active-dot"></div>
                  <svg
                    v-else-if="stepStatus(step.id) === 'failed'"
                    viewBox="0 0 24 24"
                    class="step-icon step-icon-fail"
                  >
                    <path :d="icons.close" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" />
                  </svg>
                  <span v-else class="step-number">{{ step.id }}</span>
                </div>
                <div v-if="step.id < workflowSteps.length" class="step-line" :class="lineClass(step.id)"></div>
              </div>
              <div v-show="!isCollapsed" class="step-content">
                <span class="step-label">{{ step.label }}</span>
                <span class="step-desc">{{ step.description }}</span>
              </div>
            </div>
          </template>
        </template>

        <div v-else-if="!isCollapsed" class="sidebar-empty-hint">
          从“检索整合包”或“本地导入”开始后，这里会显示当前任务的步骤和状态。
        </div>
      </section>
    </div>

    <div class="sidebar-footer">
      <button
        v-if="openSettings"
        class="sidebar-btn sidebar-settings-btn"
        @click="openSettings()"
      >
        <svg viewBox="0 0 24 24" class="sidebar-svg">
          <path :d="icons.gear" />
        </svg>
        <span v-show="!isCollapsed">设置</span>
      </button>
      <button
        class="sidebar-btn sidebar-collapse-btn"
        @click="isCollapsed = !isCollapsed"
      >
        <svg viewBox="0 0 24 24" class="sidebar-svg collapse-icon" :class="{ rotated: isCollapsed }">
          <path :d="icons.chevron" />
        </svg>
        <span v-show="!isCollapsed">收起侧栏</span>
      </button>
      <button class="sidebar-btn sidebar-theme-btn" @click="toggleDark()">
        <svg v-if="isDark" viewBox="0 0 24 24" class="sidebar-svg">
          <path :d="icons.sun" />
        </svg>
        <svg v-else viewBox="0 0 24 24" class="sidebar-svg">
          <path :d="icons.moon" />
        </svg>
        <span v-show="!isCollapsed">{{ isDark ? '浅色模式' : '深色模式' }}</span>
      </button>
    </div>
  </aside>
</template>

<style lang="scss" scoped>
.app-sidebar {
  width: $sidebar-width;
  height: 100%;
  background: linear-gradient(180deg, var(--fluent-surface-2), var(--fluent-surface-1));
  border-right: 1px solid var(--notion-hairline-soft);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
  transition: width var(--notion-transition-normal), background-color var(--notion-transition-normal);
  box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.16);
  backdrop-filter: blur(20px);

  &.collapsed {
    width: $sidebar-collapsed-width;
  }
}

.sidebar-header {
  flex-shrink: 0;
  padding: $spacing-lg $spacing-md $spacing-sm;
  border-bottom: 1px solid var(--notion-hairline-soft);
}

.sidebar-logo {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
}

.sidebar-logo-mark {
  width: 40px;
  height: 40px;
  border-radius: $rounded-md;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--fluent-surface-accent-subtle);
  border: 1px solid var(--fluent-border-accent);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.18);
}

.sidebar-logo-icon {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  color: var(--fluent-accent);
}

.sidebar-logo-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.sidebar-logo-text {
  font-family: $font-family-sans;
  font-size: $font-size-body;
  font-weight: $font-weight-semibold;
  color: var(--notion-ink);
  white-space: nowrap;
  overflow: hidden;
}

.sidebar-logo-caption {
  font-size: $font-size-micro;
  color: var(--notion-steel);
  white-space: nowrap;
}

.sidebar-workflow {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: $spacing-sm 0;
  scrollbar-width: none;
}

.sidebar-section-label {
  padding: 0 $spacing-md $spacing-sm;
  font-size: $font-size-micro-uppercase;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--notion-muted);
}

.sidebar-nav-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.task-summary-card {
  margin: 0 $spacing-xs $spacing-sm;
  padding: $spacing-sm $spacing-md;
  border-radius: var(--notion-rounded-md);
  background: linear-gradient(180deg, var(--fluent-surface-3), var(--fluent-surface-2));
  border: 1px solid var(--notion-hairline-soft);
  box-shadow: var(--notion-shadow-subtle);
}

.task-summary-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $spacing-sm;
  margin-bottom: 6px;
}

.task-summary-title {
  font-size: $font-size-body-sm;
  font-weight: $font-weight-semibold;
  color: var(--notion-ink);
}

.task-summary-progress {
  font-size: $font-size-caption;
  font-weight: $font-weight-semibold;
  color: var(--fluent-accent);
}

.task-summary-desc {
  display: block;
  font-size: $font-size-caption;
  color: var(--notion-steel);
  line-height: 1.5;
}

.sidebar-inline-action {
  width: calc(100% - #{$spacing-sm});
  margin: 0 $spacing-xs $spacing-sm;
  padding: 10px $spacing-sm;
  border-radius: var(--notion-rounded-md);
  border: 1px solid var(--notion-hairline-soft);
  background: var(--fluent-surface-2);
  color: var(--notion-ink);
  display: inline-flex;
  align-items: center;
  gap: $spacing-xs;
  cursor: pointer;
  transition: background var(--notion-transition-fast), border-color var(--notion-transition-fast);
  font: inherit;
}

.sidebar-inline-action:hover {
  background: var(--fluent-surface-accent-subtle);
  border-color: var(--fluent-border-subtle);
}

.sidebar-inline-action--collapsed {
  justify-content: center;
  padding-inline: 0;
}

.sidebar-empty-hint {
  margin: 0 $spacing-md;
  padding: $spacing-sm 0;
  font-size: $font-size-caption;
  color: var(--notion-steel);
  line-height: 1.6;
}

.step-row--nav {
  min-height: 52px;
}

.step-row {
  display: flex;
  align-items: flex-start;
  padding: 8px $spacing-md 8px $spacing-sm;
  cursor: pointer;
  border-radius: var(--notion-rounded-md);
  margin: 0 $spacing-xs;
  transition: background var(--notion-transition-fast), border-color var(--notion-transition-fast);
  min-height: 56px;
  border: 1px solid transparent;

  &:hover:not(.step-blocked) {
    background: var(--fluent-surface-accent-subtle);
    border-color: var(--fluent-border-subtle);
  }

  &.step-current {
    background: var(--fluent-surface-accent-subtle);
    border-color: var(--fluent-border-accent);
  }

  &.step-completed {
    background: var(--fluent-surface-success-subtle);
  }

  &.step-blocked {
    cursor: not-allowed;
    opacity: 0.44;
  }

  &.step-indented {
    padding-left: $spacing-xxl;
  }

  &.step-indented-deep {
    padding-left: $spacing-xxxl;
  }
}

.step-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 28px;
  min-height: 40px;
}

.step-circle {
  width: 28px;
  height: 28px;
  border-radius: var(--notion-rounded-full);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all var(--notion-transition-fast);
  position: relative;
}

.step-number {
  font-family: $font-family-sans;
  font-size: $font-size-caption;
  font-weight: $font-weight-medium;
}

.circle-pending {
  border: 1.5px solid var(--notion-hairline-strong);
  background: var(--fluent-surface-3);

  .step-number {
    color: var(--notion-steel);
  }
}

.circle-active {
  border: 1px solid var(--fluent-border-accent);
  background: var(--fluent-accent);
  box-shadow: 0 0 0 3px rgba(15, 108, 189, 0.12);

  .step-number {
    color: var(--notion-on-primary);
  }
}

.active-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--notion-rounded-full);
  background: var(--notion-on-primary);
}

.circle-completed {
  border: none;
  background: var(--notion-semantic-success);

  .step-number {
    color: var(--notion-on-primary);
  }
}

.circle-failed {
  border: 1.5px solid var(--notion-semantic-error);
  background: var(--fluent-surface-3);

  .step-number {
    color: var(--notion-semantic-error);
  }
}

.circle-blocked {
  border: 1.5px solid var(--notion-hairline);
  background: transparent;

  .step-number {
    color: var(--notion-muted);
  }
}

.step-icon {
  width: 14px;
  height: 14px;
  fill: var(--notion-on-primary);
  flex-shrink: 0;

  &.step-icon-fail {
    fill: none;
    color: var(--notion-semantic-error);
  }
}

.step-line {
  width: 2px;
  flex: 1;
  min-height: 14px;
  margin: 4px 0;
  border-radius: var(--notion-rounded-xs);
  transition: background var(--notion-transition-normal);
}

.line-completed {
  background: var(--notion-semantic-success);
}

.line-active {
  background: var(--fluent-accent);
}

.line-pending {
  background: var(--notion-hairline);
}

.step-content {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-left: $spacing-sm;
}

.step-label {
  color: var(--notion-ink);
  font-size: $font-size-body-sm;
  font-weight: $font-weight-medium;
  line-height: $line-height-body-sm;
}

.step-desc {
  color: var(--notion-steel);
  font-size: $font-size-caption;
  line-height: $line-height-caption;
}

.branch-section {
  padding: $spacing-sm $spacing-lg;
}

.branch-section-line {
  height: 1px;
  background: var(--notion-hairline-soft);
}

.branch-group {
  padding-bottom: $spacing-xs;
}

.branch-group-dimmed {
  opacity: 0.62;
}

.branch-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0 $spacing-md $spacing-xs $spacing-xxl;
  padding: 4px 8px;
  border-radius: var(--notion-rounded-full);
  font-size: $font-size-micro;
  font-weight: $font-weight-semibold;
  letter-spacing: 0.02em;
  background: var(--fluent-surface-3);
  border: 1px solid var(--notion-hairline-soft);
  color: var(--notion-steel);
}

.branch-label-active {
  border-color: var(--fluent-border-accent);
}

.branch-label-success.branch-label-active {
  color: var(--notion-semantic-success);
}

.branch-label-failure.branch-label-active {
  color: var(--notion-semantic-error);
}

.branch-label-icon {
  width: 12px;
  height: 12px;
  fill: currentColor;
}

.sidebar-footer {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: $spacing-xs;
  padding: $spacing-sm $spacing-md $spacing-md;
  border-top: 1px solid var(--notion-hairline-soft);
  background: rgba(255, 255, 255, 0.04);
}

.sidebar-btn {
  width: 100%;
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: $spacing-xs;
  padding: 0 $spacing-sm;
  border: 1px solid transparent;
  border-radius: var(--notion-rounded-sm);
  background: transparent;
  color: var(--notion-slate);
  cursor: pointer;
  transition: background var(--notion-transition-fast), color var(--notion-transition-fast), border-color var(--notion-transition-fast);

  &:hover {
    background: var(--fluent-surface-accent-subtle);
    border-color: var(--notion-hairline-soft);
    color: var(--notion-ink);
  }

  &:focus-visible {
    box-shadow: var(--fluent-focus-ring);
    outline: none;
  }
}

.sidebar-svg {
  width: 18px;
  height: 18px;
  fill: currentColor;
  flex-shrink: 0;
}

.collapse-icon {
  transition: transform var(--notion-transition-fast);

  &.rotated {
    transform: rotate(180deg);
  }
}
</style>
