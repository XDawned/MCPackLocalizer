<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ElAlert,
  ElButton,
  ElProgress,
  ElTag,
  vLoading
} from 'element-plus'
import {
  AUXILIARY_STEPS,
  WORKFLOW_STEPS,
  useWorkflowStore
} from '@/stores/workflow'

const router = useRouter()
const workflowStore = useWorkflowStore()

const allSteps = [...WORKFLOW_STEPS, ...AUXILIARY_STEPS]

const completedCount = computed(() =>
  Object.values(workflowStore.stepStatuses).filter(status => status === 'completed').length
)

const currentStepInfo = computed(() => workflowStore.currentStepInfo)
const currentStepStatus = computed(() => workflowStore.stepStatuses[workflowStore.currentStep])
const taskId = computed(() => workflowStore.currentTaskId)

const statusBadgeConfig = computed(() => {
  switch (currentStepStatus.value) {
    case 'active': return { label: '进行中', type: 'primary' }
    case 'completed': return { label: '已完成', type: 'success' }
    case 'failed': return { label: '失败', type: 'danger' }
    case 'pending': return { label: '待处理', type: 'warning' }
    case 'blocked': return { label: '未解锁', type: 'info' }
    case 'skipped': return { label: '已跳过', type: 'info' }
    default: return { label: currentStepStatus.value || '未知', type: 'info' }
  }
})

function statusTagType(stepId) {
  const status = workflowStore.stepStatuses[stepId]
  if (status === 'completed') return 'success'
  if (status === 'active') return 'primary'
  if (status === 'failed') return 'danger'
  if (status === 'pending') return 'warning'
  return 'info'
}

function statusText(stepId) {
  const status = workflowStore.stepStatuses[stepId]
  switch (status) {
    case 'completed': return '已完成'
    case 'active': return '进行中'
    case 'failed': return '失败'
    case 'pending': return '待处理'
    case 'blocked': return '未解锁'
    case 'skipped': return '已跳过'
    default: return status || '未知'
  }
}

function timelineClass(stepId) {
  const status = workflowStore.stepStatuses[stepId]
  if (status === 'completed' || status === 'skipped') return 'timeline-item--done'
  if (status === 'active') return 'timeline-item--active'
  if (status === 'failed') return 'timeline-item--fail'
  return 'timeline-item--pending'
}

function navigateToStep(stepId) {
  const location = workflowStore.goToStep(stepId)
  if (location) {
    router.push(location)
  }
}

function handleGoBack() {
  const location = workflowStore.getBackLocation()
  if (location) {
    router.push(location)
  }
}

function syncFromCurrentTask() {
  if (workflowStore.currentTaskId) {
    workflowStore.fetchWorkflowState()
  }
}

onMounted(() => {
  syncFromCurrentTask()
})
</script>

<template>
  <div
    class="workflow-view"
    v-loading="workflowStore.loading && !workflowStore.currentTaskId"
  >
    <ElAlert
      v-if="workflowStore.error"
      :title="workflowStore.error"
      type="error"
      closable
      show-icon
      class="view-alert"
    />

    <div class="page-header">
      <h1 class="page-title">本地化工作流</h1>
      <p class="page-subtitle">{{ workflowStore.workflowStateLabel }}</p>
    </div>

    <div class="progress-card">
      <div class="progress-header">
        <span class="progress-header-label">总体进度</span>
        <span class="progress-header-pct">{{ workflowStore.progressPercent }}%</span>
      </div>
      <ElProgress
        :percentage="workflowStore.progressPercent"
        :stroke-width="8"
        color="#5645d4"
      />
      <div class="progress-footer">
        {{ completedCount }} / {{ allSteps.length }} 步骤已完成
      </div>
    </div>

    <div class="step-detail-card">
      <div class="step-detail-head">
        <span class="step-detail-number">步骤 {{ workflowStore.currentStep }}</span>
        <ElTag
          :type="statusBadgeConfig.type"
          size="small"
          effect="plain"
        >
          {{ statusBadgeConfig.label }}
        </ElTag>
      </div>

      <h2 class="step-detail-title">{{ currentStepInfo.label }}</h2>
      <p class="step-detail-desc">{{ currentStepInfo.description }}</p>

      <div class="step-detail-actions">
        <ElButton
          v-if="workflowStore.currentStep > 1"
          class="notion-btn notion-btn--secondary"
          @click="handleGoBack"
        >
          返回上一步
        </ElButton>

        <ElButton
          v-if="workflowStore.isStepAccessible(workflowStore.currentStep)"
          class="notion-btn notion-btn--primary"
          @click="navigateToStep(workflowStore.currentStep)"
        >
          前往当前步骤
        </ElButton>
      </div>
    </div>

    <div class="timeline-card">
      <h3 class="timeline-card-title">任务步骤</h3>

      <div class="timeline">
        <div
          v-for="step in allSteps"
          :key="step.id"
          class="timeline-item"
          :class="timelineClass(step.id)"
        >
          <div class="timeline-node">
            <div class="timeline-dot">
              <span v-if="timelineClass(step.id) === 'timeline-item--done'" class="timeline-check">&#10003;</span>
              <span v-else-if="timelineClass(step.id) === 'timeline-item--active'" class="timeline-pulse"></span>
              <span v-else-if="timelineClass(step.id) === 'timeline-item--fail'" class="timeline-cross">&#10007;</span>
              <span v-else class="timeline-empty"></span>
            </div>
            <div
              v-if="step.id < allSteps.length"
              class="timeline-line"
              :class="{ 'timeline-line--filled': workflowStore.stepStatuses[step.id] === 'completed' }"
            />
          </div>

          <div class="timeline-body">
            <div class="timeline-body-row">
              <span class="timeline-step-name">{{ step.id }}. {{ step.label }}</span>
              <ElTag
                :type="statusTagType(step.id)"
                size="small"
                effect="plain"
              >
                {{ statusText(step.id) }}
              </ElTag>
            </div>
            <p class="timeline-step-desc">{{ step.description }}</p>

            <div class="timeline-step-actions">
              <ElButton
                v-if="workflowStore.isStepAccessible(step.id)"
                class="notion-btn notion-btn--link"
                text
                @click="navigateToStep(step.id)"
              >
                前往此步骤
              </ElButton>
              <div
                v-else-if="workflowStore.stepStatuses[step.id] === 'blocked'"
                class="timeline-step-unlock-hint"
              >
                请先完成前置步骤
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="taskId" class="task-info-card">
      <h3 class="task-info-card-title">任务信息</h3>
      <div class="task-info-grid">
        <div class="task-info-item">
          <span class="task-info-label">任务 ID</span>
          <span class="task-info-value task-info-value--mono">{{ taskId }}</span>
        </div>
        <div class="task-info-item">
          <span class="task-info-label">工作流状态</span>
          <span class="task-info-value">{{ workflowStore.workflowStateLabel }}</span>
        </div>
        <div class="task-info-item">
          <span class="task-info-label">推荐页面</span>
          <span class="task-info-value">{{ workflowStore.routeContext.recommendedRoute || currentStepInfo.route }}</span>
        </div>
        <div class="task-info-item">
          <span class="task-info-label">已恢复历史</span>
          <ElTag :type="workflowStore.routeContext.restoredFromHistory ? 'success' : 'info'" size="small">
            {{ workflowStore.routeContext.restoredFromHistory ? '是' : '否' }}
          </ElTag>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.workflow-view {
  max-width: 720px;
  margin: 0 auto;
  padding: var(--notion-spacing-xxl) var(--notion-spacing-xl) 64px;
  min-height: 100%;
}

.view-alert {
  margin-bottom: var(--notion-spacing-xl);
}

.page-header {
  margin-bottom: var(--notion-spacing-xl);
}

.page-title {
  font-size: var(--notion-font-size-h3);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0 0 var(--notion-spacing-xs) 0;
  letter-spacing: var(--notion-ls-h1);
}

.page-subtitle {
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-slate);
  margin: 0;
}

.progress-card,
.step-detail-card,
.timeline-card,
.task-info-card {
  background: var(--notion-canvas);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
  padding: var(--notion-spacing-xl);
  margin-bottom: var(--notion-spacing-md);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--notion-spacing-md);
}

.progress-header-label {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 500;
  color: var(--notion-ink);
}

.progress-header-pct {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 600;
  color: var(--notion-primary);
}

.progress-footer {
  margin-top: var(--notion-spacing-xs);
  font-size: var(--notion-font-size-caption);
  color: var(--notion-steel);
}

.step-detail-head {
  display: flex;
  align-items: center;
  gap: var(--notion-spacing-sm);
  margin-bottom: var(--notion-spacing-md);
}

.step-detail-number,
.task-info-label {
  font-size: var(--notion-font-size-micro-uppercase);
  font-weight: 600;
  color: var(--notion-stone);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.step-detail-title,
.timeline-card-title,
.task-info-card-title {
  font-size: var(--notion-font-size-h5);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0 0 var(--notion-spacing-sm) 0;
}

.step-detail-desc,
.timeline-step-desc {
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-slate);
  margin: 0;
  line-height: var(--notion-line-height-body);
}

.step-detail-actions,
.timeline-step-actions {
  display: flex;
  gap: var(--notion-spacing-sm);
  flex-wrap: wrap;
  margin-top: var(--notion-spacing-lg);
}

.timeline {
  display: flex;
  flex-direction: column;
}

.timeline-item {
  display: flex;
  gap: var(--notion-spacing-sm);
}

.timeline-item + .timeline-item {
  margin-top: var(--notion-spacing-xs);
}

.timeline-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 28px;
  flex-shrink: 0;
}

.timeline-dot {
  width: 24px;
  height: 24px;
  border-radius: var(--notion-rounded-full);
  display: flex;
  align-items: center;
  justify-content: center;
}

.timeline-item--pending .timeline-dot {
  background: var(--notion-surface);
  border: 2px solid var(--notion-muted);
}

.timeline-item--done .timeline-dot {
  background: var(--notion-brand-green);
  border: 2px solid var(--notion-brand-green);
}

.timeline-item--active .timeline-dot {
  background: var(--notion-primary);
  border: 2px solid var(--notion-primary);
  box-shadow: 0 0 0 3px rgba(86, 69, 212, 0.18);
}

.timeline-item--fail .timeline-dot {
  background: var(--notion-semantic-error);
  border: 2px solid var(--notion-semantic-error);
}

.timeline-check,
.timeline-cross {
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
}

.timeline-pulse {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #fff;
  animation: dot-pulse 1.4s ease-in-out infinite;
}

.timeline-empty {
  display: none;
}

.timeline-line {
  width: 2px;
  flex: 1;
  min-height: 28px;
  background: var(--notion-hairline);
  margin-top: 4px;
  border-radius: 1px;
}

.timeline-line--filled {
  background: var(--notion-brand-green);
}

.timeline-body {
  flex: 1;
  min-width: 0;
  padding: 2px 0 var(--notion-spacing-lg) 0;
}

.timeline-item:last-child .timeline-body {
  padding-bottom: 0;
}

.timeline-body-row {
  display: flex;
  align-items: center;
  gap: var(--notion-spacing-xs);
  flex-wrap: wrap;
}

.timeline-step-name,
.task-info-value {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 600;
  color: var(--notion-ink);
}

.timeline-step-unlock-hint {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-brand-orange);
  background: var(--notion-tint-peach);
  border-radius: var(--notion-rounded-sm);
  padding: var(--notion-spacing-xxs) var(--notion-spacing-xs);
}

.task-info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--notion-spacing-md);
}

.task-info-item {
  display: flex;
  flex-direction: column;
  gap: var(--notion-spacing-xxs);
}

.task-info-value--mono {
  font-family: 'JetBrains Mono', 'Cascadia Code', 'Consolas', 'Monaco', monospace;
  font-size: var(--notion-font-size-caption);
}

.notion-btn {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 500;
  border-radius: var(--notion-rounded-md);
  padding: 8px 18px;
  height: auto;
  line-height: var(--notion-line-height-button);
  transition: all var(--notion-transition-normal);
  border: 1px solid transparent;
}

.notion-btn--primary {
  background: var(--notion-primary);
  border-color: var(--notion-primary);
  color: var(--notion-on-primary);
}

.notion-btn--primary:hover {
  background: var(--notion-primary-pressed);
  border-color: var(--notion-primary-pressed);
  color: var(--notion-on-primary);
}

.notion-btn--secondary {
  background: transparent;
  border-color: var(--notion-hairline-strong);
  color: var(--notion-ink);
}

.notion-btn--secondary:hover,
.notion-btn--link:hover {
  background: var(--notion-surface);
  border-color: var(--notion-steel);
  color: var(--notion-ink);
}

.notion-btn--link {
  padding: 0;
  border: none;
  color: var(--notion-primary);
}

@keyframes dot-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.5); opacity: 0.5; }
}

@media (max-width: 640px) {
  .workflow-view {
    padding: var(--notion-spacing-xl) var(--notion-spacing-md) 48px;
  }

  .task-info-grid {
    grid-template-columns: 1fr;
  }
}
</style>
