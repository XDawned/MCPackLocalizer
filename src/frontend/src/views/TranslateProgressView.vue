<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElButton, ElProgress, ElTag, ElAlert, ElEmpty, vLoading } from 'element-plus'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { useTranslateStore } from '@/stores/translate'
import { useWorkflowStore } from '@/stores/workflow'
import { useWebSocket } from '@/composables/useWebSocket'

const route = useRoute()
const router = useRouter()
const translateStore = useTranslateStore()
const workflowStore = useWorkflowStore()

const taskId = computed(() => route.query.taskId || translateStore.currentTaskId)
const ws = useWebSocket(taskId)

const terminalContainer = ref(null)
let terminal = null
let renderedLogCount = 0

const stages = [
  { key: 'extracting', label: '提取中' },
  { key: 'translating', label: '翻译中' },
  { key: 'post_processing', label: '后处理' },
  { key: 'assembling', label: '组装中' }
]

const stageMap = {
  started: 0,
  extracting: 0,
  translating: 1,
  post_processing: 2,
  assembling: 3,
  complete: 4,
  done: 4,
  cancelled: 4,
  failed: 4
}

const hasTaskContext = computed(() => {
  return Boolean(taskId.value || translateStore.streaming || translateStore.logs.length > 0 || translateStore.error)
})

const currentStageKey = computed(() => {
  const progressStage = translateStore.progress.stage
  if (progressStage === 'done') return 'complete'
  return progressStage || translateStore.taskStatus?.stage || ''
})

const currentStageIndex = computed(() => {
  return stageMap[currentStageKey.value] ?? -1
})

function getStageClass(index) {
  if (index < currentStageIndex.value) return 'completed'
  if (index === currentStageIndex.value) return 'active'
  return 'pending'
}

const statusConfig = computed(() => {
  const status = translateStore.taskStatus?.status

  if (status === 'paused') return { label: '已暂停', type: 'warning' }
  if (status === 'failed') return { label: '失败', type: 'danger' }
  if (status === 'cancelled') return { label: '已取消', type: 'info' }
  if (['ready_to_apply', 'completed'].includes(status) || translateStore.progress.stage === 'complete') {
    return { label: '已完成', type: 'success' }
  }
  if (translateStore.streaming || ['pending', 'running', 'configuring', 'extracting', 'translating', 'assembling'].includes(status)) {
    return { label: '运行中', type: 'success' }
  }
  return { label: status || '未知', type: '' }
})

const percentage = computed(() => {
  const p = translateStore.progress
  if (!p.total_items || p.total_items === 0) return 0
  return Math.round((p.completed_items / p.total_items) * 100)
})

const areaProgresses = computed(() => translateStore.progress.areas || [])
const errorItems = computed(() => translateStore.progress.errors || [])
const hasAreaProgress = computed(() => areaProgresses.value.length > 0)
const hasErrors = computed(() => errorItems.value.length > 0)
const failedItemsCount = computed(() => translateStore.progress.failed_items || errorItems.value.length || 0)
const failedBatchCount = computed(() => translateStore.progress.failed_batches || 0)

const isActive = computed(() => {
  const status = translateStore.taskStatus?.status
  if (status === 'paused') return false
  if (translateStore.streaming) return true
  return ['pending', 'running', 'configuring', 'extracting', 'translating', 'assembling'].includes(status)
})

const isPaused = computed(() => translateStore.taskStatus?.status === 'paused')
const isComplete = computed(() => {
  const status = translateStore.taskStatus?.status
  return ['ready_to_apply', 'completed'].includes(status) || translateStore.progress.stage === 'complete'
})
const isFailed = computed(() => translateStore.taskStatus?.status === 'failed')
const isCancelled = computed(() => translateStore.taskStatus?.status === 'cancelled')
const isTerminal = computed(() => isComplete.value || isFailed.value || isCancelled.value)
const showLogTerminal = computed(() => Boolean(taskId.value || translateStore.logs.length > 0 || translateStore.streamMessage || isTerminal.value))

function formatTokens(n) {
  if (n == null) return '0'
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

function formatSeconds(sec) {
  if (sec == null || sec < 0) return '00:00:00'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

const LOG_LEVEL_COLORS = {
  DEBUG: '\x1b[90m',
  INFO: '\x1b[32m',
  WARN: '\x1b[33m',
  ERROR: '\x1b[31m'
}

const RESET_COLOR = '\x1b[0m'

function normalizeLogLevel(level) {
  const normalized = String(level || 'INFO').toUpperCase()
  return normalized === 'WARNING' ? 'WARN' : normalized
}

function colorizeLine(level, text) {
  const normalized = normalizeLogLevel(level)
  const color = LOG_LEVEL_COLORS[normalized]
  return color ? `${color}${text}${RESET_COLOR}` : text
}

function createTerminal() {
  if (terminal || !terminalContainer.value) return

  terminal = new Terminal({
    convertEol: true,
    disableStdin: true,
    cursorBlink: false,
    fontSize: 12,
    lineHeight: 1.35,
    fontFamily: 'Consolas, "Cascadia Mono", "Microsoft YaHei UI Mono", monospace',
    scrollback: 5000,
    theme: {
      background: '#0b1220',
      foreground: '#dbe4f0',
      cursor: '#93c5fd',
      selectionBackground: 'rgba(148, 163, 184, 0.28)',
      black: '#0f172a',
      red: '#f87171',
      green: '#4ade80',
      yellow: '#facc15',
      blue: '#60a5fa',
      magenta: '#c084fc',
      cyan: '#22d3ee',
      white: '#e5e7eb',
      brightBlack: '#64748b',
      brightRed: '#fca5a5',
      brightGreen: '#86efac',
      brightYellow: '#fde68a',
      brightBlue: '#93c5fd',
      brightMagenta: '#d8b4fe',
      brightCyan: '#67e8f9',
      brightWhite: '#f8fafc'
    }
  })

  terminal.open(terminalContainer.value)
  renderedLogCount = 0
}

function disposeTerminal() {
  if (terminal) {
    terminal.dispose()
    terminal = null
  }
  renderedLogCount = 0
}

function writeTerminalLine(logEntry) {
  if (!terminal || !logEntry) return
  const line = logEntry.formatted || logEntry.message || String(logEntry)
  terminal.writeln(colorizeLine(logEntry.level, line))
  terminal.scrollToBottom()
}

function writeTerminalPlaceholder() {
  if (!terminal) return
  terminal.writeln('\x1b[90m等待实时日志输出...\x1b[0m')
}

function syncTerminalLogs() {
  if (!terminal) return

  if (translateStore.logs.length === 0) {
    terminal.clear()
    renderedLogCount = 0
    writeTerminalPlaceholder()
    return
  }

  if (translateStore.logs.length < renderedLogCount) {
    terminal.clear()
    renderedLogCount = 0
  }

  while (renderedLogCount < translateStore.logs.length) {
    writeTerminalLine(translateStore.logs[renderedLogCount])
    renderedLogCount += 1
  }
}

async function ensureTerminalReady() {
  if (!showLogTerminal.value) return
  await nextTick()
  if (!terminalContainer.value) return
  if (!terminal) {
    createTerminal()
  }
  syncTerminalLogs()
}

watch(() => ws.progress.value, (event) => {
  if (event) {
    translateStore.applyProgressEvent(event)
  }
}, { deep: true })

watch(() => ws.logEvent.value, (event) => {
  if (event) {
    translateStore.handleLogEvent(event)
  }
})

watch(() => ws.errorEvent.value, (event) => {
  if (event) {
    translateStore.handleErrorEvent(event)
  }
})

watch(() => ws.doneEvent.value, (event) => {
  if (event) {
    translateStore.handleDoneEvent(event)
  }
})

watch([taskId, () => translateStore.streaming], ([id, streaming]) => {
  if (!id) return

  if (streaming) {
    translateStore.stopPolling()
    ws.disconnect()
    return
  }

  translateStore.currentTaskId = id
  translateStore.pollStatus(id)
  ws.disconnect()
  ws.connect()
}, { immediate: true })

watch(() => translateStore.logs.length, async () => {
  await ensureTerminalReady()
  syncTerminalLogs()
}, { immediate: true })

watch(showLogTerminal, async (visible) => {
  if (visible) {
    await ensureTerminalReady()
  }
})

onMounted(async () => {
  syncWorkflowContext()
  await ensureTerminalReady()
})

onUnmounted(() => {
  translateStore.stopPolling()
  ws.disconnect()
  disposeTerminal()
})

function handlePause() {
  translateStore.pauseTranslation()
}

function handleResume() {
  translateStore.resumeTranslation()
}

function handleCancel() {
  translateStore.cancelTranslation()
}

function syncWorkflowContext() {
  workflowStore.updateRouteContext({
    taskId: taskId.value || null,
    modpackVersionId: route.query.modpackVersionId,
    localPath: route.query.localPath,
    scanId: route.query.scanId
  })
}

function navigateToStep(stepId) {
  syncWorkflowContext()
  router.push(
    workflowStore.getStepLocation(stepId, {
      taskId: taskId.value || null,
      modpackVersionId: route.query.modpackVersionId,
      localPath: route.query.localPath,
      scanId: route.query.scanId
    })
  )
}

function goReview() {
  navigateToStep(5)
}

function goApply() {
  navigateToStep(4)
}
</script>

<template>
  <div class="translate-progress-view" v-loading="translateStore.loading && !translateStore.taskStatus && !translateStore.streaming">
    <ElEmpty v-if="!hasTaskContext" description="请从翻译配置页启动翻译任务" />

    <template v-else>
      <ElAlert
        v-if="translateStore.error"
        :title="translateStore.error"
        type="error"
        closable
        show-icon
        class="view-alert"
      />

      <template v-if="isCancelled">
        <div class="page-header">
          <h1 class="page-title">翻译进度</h1>
        </div>

        <div class="terminal-card terminal-card--cancelled">
          <div class="terminal-icon">⏹</div>
          <h2 class="terminal-heading">翻译已取消</h2>
          <p class="terminal-desc">任务已被手动终止，已生成的日志会保留在下方终端区域。</p>
          <ElButton class="notion-btn notion-btn--primary" @click="router.push('/')">返回首页</ElButton>
        </div>
      </template>

      <template v-else-if="isComplete">
        <div class="page-header">
          <h1 class="page-title">翻译进度</h1>
        </div>

        <div class="terminal-card terminal-card--success">
          <div class="terminal-icon terminal-icon--success">
            <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
              <circle cx="32" cy="32" r="28" fill="#d9f3e1" />
              <path d="M19 33l8 8 18-18" stroke="#1aae39" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <h2 class="terminal-heading">翻译完成</h2>
          <p class="terminal-desc">整合包内容已全部翻译完毕，历史日志已保留。</p>

          <div class="completion-stats">
            <div class="completion-stat">
              <span class="completion-stat-label">总条目</span>
              <span class="completion-stat-value">{{ translateStore.progress.total_items }}</span>
            </div>
            <div class="completion-stat-divider" />
            <div class="completion-stat">
              <span class="completion-stat-label">失败条目</span>
              <span class="completion-stat-value">{{ failedItemsCount }}</span>
            </div>
            <div class="completion-stat-divider" />
            <div class="completion-stat">
              <span class="completion-stat-label">Token 消耗</span>
              <span class="completion-stat-value">{{ formatTokens(translateStore.progress.tokens_consumed) }}</span>
            </div>
            <div class="completion-stat-divider" />
            <div class="completion-stat">
              <span class="completion-stat-label">预估费用</span>
              <span class="completion-stat-value">${{ translateStore.progress.estimated_cost?.toFixed(2) || '0.00' }}</span>
            </div>
          </div>

          <div class="terminal-actions">
            <ElButton class="notion-btn notion-btn--secondary" @click="goReview">查看结果</ElButton>
            <ElButton class="notion-btn notion-btn--primary" @click="goApply">应用翻译</ElButton>
          </div>
        </div>
      </template>

      <template v-else>
        <div class="page-header">
          <div class="page-header-row">
            <h1 class="page-title">翻译进度</h1>
            <div class="task-meta">
              <span class="task-id" v-if="taskId">任务 {{ taskId }}</span>
              <ElTag v-if="statusConfig.label" :type="statusConfig.type" size="small">
                {{ statusConfig.label }}
              </ElTag>
            </div>
          </div>
        </div>

        <div class="stage-bar">
          <div
            v-for="(stage, i) in stages"
            :key="stage.key"
            class="stage-node"
            :class="getStageClass(i)"
          >
            <div class="stage-dot">
              <span v-if="getStageClass(i) === 'completed'" class="stage-check">&#10003;</span>
              <span v-else-if="getStageClass(i) === 'active'" class="stage-pulse"></span>
              <span v-else class="stage-empty"></span>
            </div>
            <span class="stage-label">{{ stage.label }}</span>
          </div>
        </div>

        <div class="progress-card">
          <div class="progress-header">
            <span class="progress-label">翻译进度</span>
            <span class="progress-pct">{{ percentage }}%</span>
          </div>
          <ElProgress
            :percentage="percentage"
            :stroke-width="8"
            color="#5645d4"
          />
          <div class="progress-sub">
            {{ translateStore.progress.completed_items }} / {{ translateStore.progress.total_items }} 条已处理
          </div>

          <div class="progress-stream-message" v-if="translateStore.streamMessage">
            {{ translateStore.streamMessage }}
          </div>

          <div class="progress-stats">
            <div class="progress-stat">
              <span class="progress-stat-label">总条目</span>
              <span class="progress-stat-value">{{ translateStore.progress.total_items }}</span>
            </div>
            <div class="progress-stat">
              <span class="progress-stat-label">已完成</span>
              <span class="progress-stat-value">{{ translateStore.progress.completed_items }}</span>
            </div>
            <div class="progress-stat" v-if="translateStore.progress.current_file">
              <span class="progress-stat-label">当前文件</span>
              <span class="progress-stat-value progress-stat-value--file">{{ translateStore.progress.current_file }}</span>
            </div>
            <div class="progress-stat">
              <span class="progress-stat-label">耗时</span>
              <span class="progress-stat-value">{{ formatSeconds(translateStore.progress.elapsed_seconds) }}</span>
            </div>
          </div>
        </div>

        <div class="area-progress-card" v-if="hasAreaProgress">
          <div class="area-progress-header">
            <span class="area-progress-title">分区进度</span>
          </div>
          <div class="area-progress-list">
            <div
              v-for="area in areaProgresses"
              :key="area.type"
              class="area-progress-item"
            >
              <div class="area-progress-item-hd">
                <span class="area-progress-item-label">{{ area.label || area.type }}</span>
                <span class="area-progress-item-count">{{ area.completed || 0 }} / {{ area.total || 0 }}</span>
              </div>
              <ElProgress
                :percentage="area.total ? Math.round((area.completed / area.total) * 100) : 0"
                :stroke-width="4"
                :color="area.type === 'ftb_quests' ? '#1aae39' : area.type === 'better_questing' ? '#f59e0b' : '#5645d4'"
              />
            </div>
          </div>
        </div>

        <div class="error-card" v-if="hasErrors">
          <div class="error-card-header">
            <svg class="error-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span class="error-card-title">翻译异常条目</span>
            <span class="error-card-count">{{ errorItems.length }} 条</span>
          </div>
          <ul class="error-list">
            <li
              v-for="(err, idx) in errorItems.slice(0, 10)"
              :key="idx"
              class="error-item"
            >
              <span class="error-item-file">{{ err.source_file || err.key || '-' }}</span>
              <span class="error-item-msg">{{ err.message || err.original_text || '未知错误' }}</span>
            </li>
          </ul>
          <p class="error-list-more" v-if="errorItems.length > 10">
            等 {{ errorItems.length }} 条异常...
          </p>
        </div>

        <div class="stats-card">
          <div class="stats-item">
            <span class="stats-item-label">Token 消耗量</span>
            <span class="stats-item-value">{{ formatTokens(translateStore.progress.tokens_consumed) }}</span>
          </div>
          <div class="stats-divider" />
          <div class="stats-item">
            <span class="stats-item-label">已用时间</span>
            <span class="stats-item-value">{{ formatSeconds(translateStore.progress.elapsed_seconds) }}</span>
          </div>
          <div class="stats-divider" />
          <div class="stats-item">
            <span class="stats-item-label">失败条目</span>
            <span class="stats-item-value">{{ failedItemsCount }}</span>
          </div>
          <div class="stats-divider" />
          <div class="stats-item">
            <span class="stats-item-label">失败批次</span>
            <span class="stats-item-value">{{ failedBatchCount }}</span>
          </div>
        </div>

        <div class="controls-row" v-if="!isTerminal">
          <ElButton
            v-if="isActive"
            plain
            class="notion-btn notion-btn--warn"
            @click="handlePause"
          >
            暂停
          </ElButton>

          <ElButton
            v-if="isPaused"
            type="primary"
            class="notion-btn notion-btn--primary"
            @click="handleResume"
          >
            继续
          </ElButton>

          <ElButton
            type="danger"
            plain
            class="notion-btn notion-btn--danger"
            @click="handleCancel"
          >
            终止
          </ElButton>
        </div>

        <div v-if="isFailed" class="terminal-card terminal-card--error">
          <div class="terminal-icon">&#10007;</div>
          <h2 class="terminal-heading">翻译失败</h2>
          <p class="terminal-desc">{{ translateStore.taskStatus?.error || '任务执行过程中发生错误' }}</p>
          <ElButton class="notion-btn notion-btn--primary" @click="router.push('/')">返回首页</ElButton>
        </div>

        <div class="ws-indicator" v-if="taskId && !isTerminal && !translateStore.streaming">
          <span class="ws-dot" :class="{ 'ws-dot--connected': ws.connected.value }" />
          <span class="ws-text">{{ ws.connected.value ? '实时连接已建立' : '正在连接...' }}</span>
        </div>
      </template>

      <div v-if="showLogTerminal" class="log-card">
        <div class="log-card-header">
          <div>
            <h3 class="log-card-title">实时日志终端</h3>
            <p class="log-card-desc">展示后端通过 SSE / WebSocket 推送的结构化日志，任务结束后仍保留历史。</p>
          </div>
          <div class="log-card-meta">
            <span class="log-meta-chip">{{ translateStore.logs.length }} 行日志</span>
            <span class="log-meta-chip" v-if="failedItemsCount > 0">失败条目 {{ failedItemsCount }}</span>
            <span class="log-meta-chip" v-if="failedBatchCount > 0">失败批次 {{ failedBatchCount }}</span>
          </div>
        </div>
        <div class="log-card-body">
          <div ref="terminalContainer" class="log-terminal" />
        </div>
      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.translate-progress-view {
  max-width: 960px;
  margin: 0 auto;
  padding: var(--notion-spacing-xxl) var(--notion-spacing-xl);
  min-height: 100%;
}

.view-alert {
  margin-bottom: var(--notion-spacing-xl);
}

.page-header {
  margin-bottom: var(--notion-spacing-xl);
}

.page-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--notion-spacing-sm);
}

.page-title {
  font-size: var(--notion-font-size-h3);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0;
  letter-spacing: var(--notion-ls-h1);
}

.task-meta {
  display: flex;
  align-items: center;
  gap: var(--notion-spacing-sm);
}

.task-id {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-steel);
  background: var(--notion-surface);
  padding: var(--notion-spacing-xxs) var(--notion-spacing-sm);
  border-radius: var(--notion-rounded-sm);
  border: 1px solid var(--notion-hairline);
  font-family: var(--notion-font-sans);
}

.stage-bar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0;
  margin-bottom: var(--notion-spacing-xl);
  position: relative;

  &::before {
    content: '';
    position: absolute;
    top: 12px;
    left: 0;
    right: 0;
    height: 2px;
    background: var(--notion-hairline);
    z-index: 0;
  }
}

.stage-node {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--notion-spacing-xs);
  flex: 1;
}

.stage-dot {
  width: 24px;
  height: 24px;
  border-radius: var(--notion-rounded-full);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--notion-transition-normal);
}

.stage-node.pending .stage-dot {
  background: var(--notion-surface);
  border: 2px solid var(--notion-muted);
}

.stage-node.completed .stage-dot {
  background: var(--notion-brand-green);
  border: 2px solid var(--notion-brand-green);
}

.stage-node.active .stage-dot {
  background: var(--notion-primary);
  border: 2px solid var(--notion-primary);
}

.stage-check {
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
}

.stage-pulse {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #fff;
  animation: dot-pulse 1.4s ease-in-out infinite;
}

.stage-empty {
  display: none;
}

.stage-label {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-muted);
  white-space: nowrap;
  transition: color var(--notion-transition-normal);
}

.stage-node.completed .stage-label {
  color: var(--notion-brand-green);
}

.stage-node.active .stage-label {
  color: var(--notion-primary);
  font-weight: 600;
}

@keyframes dot-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.6); opacity: 0.5; }
}

.progress-card {
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

.progress-label {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 500;
  color: var(--notion-ink);
}

.progress-pct {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 600;
  color: var(--notion-primary);
  font-family: var(--notion-font-sans);
}

.progress-sub {
  margin-top: var(--notion-spacing-xs);
  font-size: var(--notion-font-size-caption);
  color: var(--notion-steel);
}

.progress-stream-message {
  margin-top: var(--notion-spacing-xs);
  font-size: var(--notion-font-size-caption);
  color: var(--notion-primary);
  font-style: italic;
  animation: pulse-opacity 1.5s ease-in-out infinite;
}

@keyframes pulse-opacity {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.progress-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--notion-spacing-md);
  margin-top: var(--notion-spacing-lg);
  padding-top: var(--notion-spacing-md);
  border-top: 1px solid var(--notion-hairline);
}

.progress-stat {
  display: flex;
  flex-direction: column;
  gap: var(--notion-spacing-xxs);
}

.progress-stat-label {
  font-size: var(--notion-font-size-micro-uppercase);
  font-weight: 600;
  color: var(--notion-stone);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.progress-stat-value {
  font-size: var(--notion-font-size-h5);
  font-weight: 700;
  color: var(--notion-ink);
  line-height: 1.2;
}

.progress-stat-value--file {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-slate);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stats-card {
  background: var(--notion-surface);
  border-radius: var(--notion-rounded-lg);
  padding: var(--notion-spacing-lg) var(--notion-spacing-xl);
  display: flex;
  align-items: center;
  margin-bottom: var(--notion-spacing-xl);
}

.stats-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--notion-spacing-xxs);
}

.stats-item-label {
  font-size: var(--notion-font-size-micro-uppercase);
  font-weight: 600;
  color: var(--notion-stone);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.stats-item-value {
  font-size: var(--notion-font-size-h5);
  font-weight: 700;
  color: var(--notion-charcoal);
  font-family: var(--notion-font-sans);
}

.area-progress-card {
  background: var(--notion-canvas);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
  padding: var(--notion-spacing-lg);
  margin-bottom: var(--notion-spacing-md);
}

.area-progress-header {
  margin-bottom: var(--notion-spacing-md);
}

.area-progress-title {
  font-size: var(--notion-font-size-body);
  font-weight: 600;
  color: var(--notion-ink);
}

.area-progress-list {
  display: flex;
  flex-direction: column;
  gap: var(--notion-spacing-md);
}

.area-progress-item {
  display: flex;
  flex-direction: column;
  gap: var(--notion-spacing-xs);
}

.area-progress-item-hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.area-progress-item-label {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 500;
  color: var(--notion-charcoal);
}

.area-progress-item-count {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-steel);
  font-family: var(--notion-font-sans);
}

.error-card {
  background: var(--notion-canvas);
  border: 1px solid var(--notion-semantic-error);
  border-radius: var(--notion-rounded-lg);
  padding: var(--notion-spacing-lg);
  margin-bottom: var(--notion-spacing-md);
}

.error-card-header {
  display: flex;
  align-items: center;
  gap: var(--notion-spacing-xs);
  margin-bottom: var(--notion-spacing-md);
  padding-bottom: var(--notion-spacing-sm);
  border-bottom: 1px solid var(--notion-hairline);
}

.error-card-icon {
  width: 18px;
  height: 18px;
  color: var(--notion-semantic-error);
  flex-shrink: 0;
}

.error-card-title {
  font-size: var(--notion-font-size-body);
  font-weight: 600;
  color: var(--notion-ink);
  flex: 1;
}

.error-card-count {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-semantic-error);
  background: var(--notion-brand-red100);
  padding: 2px 8px;
  border-radius: var(--notion-rounded-sm);
  font-weight: 600;
}

.error-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--notion-spacing-xs);
}

.error-item {
  display: flex;
  align-items: flex-start;
  gap: var(--notion-spacing-sm);
  padding: var(--notion-spacing-xs);
  border-radius: var(--notion-rounded-sm);
  font-size: var(--notion-font-size-micro);
  line-height: 1.5;

  &:hover {
    background: var(--notion-surface);
  }
}

.error-item-file {
  color: var(--notion-charcoal);
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.error-item-msg {
  color: var(--notion-slate);
  flex: 1;
  min-width: 0;
}

.error-list-more {
  margin: var(--notion-spacing-sm) 0 0;
  font-size: var(--notion-font-size-micro);
  color: var(--notion-muted);
  text-align: center;
}

.stats-divider {
  width: 1px;
  height: 36px;
  background: var(--notion-hairline);
  flex-shrink: 0;
}

.controls-row {
  display: flex;
  gap: var(--notion-spacing-sm);
  margin-bottom: var(--notion-spacing-xl);
}

.terminal-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: var(--notion-spacing-section-sm) var(--notion-spacing-xl);
  background: var(--notion-canvas);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
  animation: fadeInUp 0.5s ease-out;
  margin-bottom: var(--notion-spacing-xl);
}

.terminal-card--success {
  border-color: var(--notion-brand-green);
}

.terminal-card--error {
  border-color: var(--notion-semantic-error);
}

.terminal-card--cancelled {
  border-color: var(--notion-muted);
}

.terminal-icon {
  font-size: 48px;
  margin-bottom: var(--notion-spacing-md);
  color: var(--notion-muted);
}

.terminal-icon--success {
  animation: pulse-glow 2s ease-in-out infinite;
}

.terminal-heading {
  font-size: var(--notion-font-size-h3);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0 0 var(--notion-spacing-xs) 0;
}

.terminal-desc {
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-slate);
  margin: 0 0 var(--notion-spacing-xxl) 0;
}

@keyframes pulse-glow {
  0%, 100% { filter: drop-shadow(0 0 6px rgba(26, 174, 57, 0.3)); }
  50% { filter: drop-shadow(0 0 18px rgba(26, 174, 57, 0.55)); }
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.completion-stats {
  display: flex;
  align-items: center;
  background: var(--notion-surface);
  border-radius: var(--notion-rounded-md);
  border: 1px solid var(--notion-hairline);
  padding: var(--notion-spacing-lg) var(--notion-spacing-xl);
  margin-bottom: var(--notion-spacing-xxl);
  flex-wrap: wrap;
  justify-content: center;
}

.completion-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--notion-spacing-xxs);
  padding: 0 var(--notion-spacing-lg);
}

.completion-stat-label {
  font-size: var(--notion-font-size-micro-uppercase);
  font-weight: 600;
  color: var(--notion-stone);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.completion-stat-value {
  font-size: var(--notion-font-size-h4);
  font-weight: 700;
  color: var(--notion-ink);
}

.completion-stat-divider {
  width: 1px;
  height: 36px;
  background: var(--notion-hairline);
  flex-shrink: 0;
}

.terminal-actions {
  display: flex;
  gap: var(--notion-spacing-md);
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

  &:hover {
    background: var(--notion-primary-pressed);
    border-color: var(--notion-primary-pressed);
    color: var(--notion-on-primary);
  }
}

.notion-btn--secondary {
  background: transparent;
  border-color: var(--notion-hairline-strong);
  color: var(--notion-ink);

  &:hover {
    background: var(--notion-surface);
    border-color: var(--notion-steel);
    color: var(--notion-ink);
  }
}

.notion-btn--warn {
  background: transparent;
  border-color: var(--notion-brand-orange);
  color: var(--notion-brand-orange);

  &:hover {
    background: var(--notion-brand-orange);
    border-color: var(--notion-brand-orange);
    color: #fff;
  }
}

.notion-btn--danger {
  background: transparent;
  border-color: var(--notion-semantic-error);
  color: var(--notion-semantic-error);

  &:hover {
    background: var(--notion-semantic-error);
    border-color: var(--notion-semantic-error);
    color: #fff;
  }
}

.log-card {
  background: var(--notion-canvas);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
  padding: var(--notion-spacing-lg);
  margin-top: var(--notion-spacing-lg);
}

.log-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--notion-spacing-md);
  margin-bottom: var(--notion-spacing-md);
}

.log-card-title {
  margin: 0 0 6px;
  font-size: var(--notion-font-size-body);
  font-weight: 600;
  color: var(--notion-ink);
}

.log-card-desc {
  margin: 0;
  font-size: var(--notion-font-size-caption);
  color: var(--notion-steel);
  line-height: 1.5;
}

.log-card-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.log-meta-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: var(--notion-rounded-sm);
  background: var(--notion-surface);
  border: 1px solid var(--notion-hairline);
  color: var(--notion-slate);
  font-size: var(--notion-font-size-micro);
  white-space: nowrap;
}

.log-card-body {
  border-radius: var(--notion-rounded-md);
  overflow: hidden;
  border: 1px solid rgba(15, 23, 42, 0.1);
}

.log-terminal {
  height: 340px;
  padding: 10px;
  background: #0b1220;
}

:deep(.log-terminal .xterm) {
  height: 100%;
}

:deep(.log-terminal .xterm-viewport) {
  overflow-y: auto !important;
}

.ws-indicator {
  display: flex;
  align-items: center;
  gap: var(--notion-spacing-xs);
  padding-top: var(--notion-spacing-md);
  margin-top: var(--notion-spacing-md);
  border-top: 1px solid var(--notion-hairline-soft);
}

.ws-dot {
  width: 6px;
  height: 6px;
  border-radius: var(--notion-rounded-full);
  background: var(--notion-muted);
  transition: background var(--notion-transition-normal);
}

.ws-dot--connected {
  background: var(--notion-brand-green);
}

.ws-text {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-stone);
}

@media (max-width: 768px) {
  .progress-stats {
    grid-template-columns: repeat(2, 1fr);
  }

  .stats-card {
    flex-wrap: wrap;
    gap: var(--notion-spacing-md);
  }

  .stats-divider {
    display: none;
  }

  .log-card-header {
    flex-direction: column;
  }

  .log-card-meta {
    justify-content: flex-start;
  }
}

@media (max-width: 640px) {
  .translate-progress-view {
    padding: var(--notion-spacing-lg) var(--notion-spacing-md);
  }

  .stats-card {
    flex-direction: column;
  }

  .completion-stats {
    flex-direction: column;
    gap: var(--notion-spacing-md);
    padding: var(--notion-spacing-lg);
  }

  .completion-stat-divider {
    width: 100%;
    height: 1px;
  }

  .controls-row,
  .terminal-actions {
    flex-direction: column;
    width: 100%;
  }

  .terminal-actions .notion-btn,
  .controls-row .notion-btn {
    width: 100%;
  }

  .log-terminal {
    height: 280px;
  }
}
</style>
