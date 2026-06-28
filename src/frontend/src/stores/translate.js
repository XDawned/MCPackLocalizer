import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import {
  saveTranslateConfig,
  startTranslation as startTranslationApi,
  startTranslationStream,
  getTranslateStatus,
  pauseTranslation as pauseTranslationApi,
  resumeTranslation as resumeTranslationApi,
  cancelTranslation as cancelTranslationApi,
  getTranslateItems
} from '@/api/translate'

let pollingTimer = null

const DEFAULT_BATCH_RETRY_LIMIT = 3

function createDefaultConfig() {
  return {
    keep_original: true,
    enable_cache: true,
    cache_scope: 'version',
    cache_reference_ids: [],
    ai_provider: 'openai',
    ai_model: 'deepseek-v4-flash',
    enable_glossary: true,
    batch_size: 200,
    concurrency: 2,
    batch_retry_limit: DEFAULT_BATCH_RETRY_LIMIT,
    custom_prompt: ''
  }
}

function createDefaultProgress() {
  return {
    stage: '',
    total_items: 0,
    completed_items: 0,
    current_file: '',
    tokens_consumed: 0,
    estimated_cost: 0,
    elapsed_seconds: 0,
    failed_items: 0,
    failed_batches: 0,
    errors: []
  }
}

function normalizeRetryLimit(value, fallback = DEFAULT_BATCH_RETRY_LIMIT) {
  const parsed = Number.parseInt(String(value ?? fallback), 10)
  if (Number.isNaN(parsed)) return fallback
  return Math.min(3, Math.max(0, parsed))
}

function normalizeLogLevel(level = 'INFO') {
  const normalized = String(level || 'INFO').toUpperCase()
  return normalized === 'WARNING' ? 'WARN' : normalized
}

function formatLogTimestamp(timestamp) {
  const source = timestamp ? String(timestamp) : new Date().toISOString()
  return source.replace('T', ' ').substring(0, 19)
}

function formatLogContext(context = {}) {
  if (!context || typeof context !== 'object' || Array.isArray(context)) {
    return ''
  }

  const contextParts = []

  if (context.batch_index !== undefined || context.total_batches !== undefined) {
    contextParts.push(`批次 ${context.batch_index ?? '-'}\/${context.total_batches ?? '-'}`)
  }

  if (context.retry_attempt !== undefined || context.max_retry !== undefined) {
    contextParts.push(`重试 ${context.retry_attempt ?? '-'}\/${context.max_retry ?? '-'}`)
  }

  const labels = {
    original_text: '原文',
    translated_text: '译文',
    error: '错误',
    error_type: '错误类型'
  }

  const reservedKeys = ['batch_index', 'total_batches', 'retry_attempt', 'max_retry']
  const extraContext = Object.entries(context)
    .filter(([key, value]) => value !== undefined && value !== null && value !== '' && !reservedKeys.includes(key))
    .map(([key, value]) => {
      const rendered = Array.isArray(value) ? value.join(', ') : value
      return `${labels[key] || key}:${String(rendered)}`
    })

  if (extraContext.length > 0) {
    contextParts.push(extraContext.join(', '))
  }

  return contextParts.join('；')
}

function formatLogEntry(entry) {
  if (entry && typeof entry === 'object' && entry.level && entry.timestamp) {
    const time = formatLogTimestamp(entry.timestamp)
    const contextStr = formatLogContext(entry.context)
    const contextPart = contextStr ? `【${contextStr}】` : ''
    return `【${normalizeLogLevel(entry.level)}】【${time}】${contextPart}${entry.message || ''}`
  }

  if (typeof entry === 'string') return entry
  if (entry && typeof entry === 'object' && entry.message) return entry.message
  return String(entry ?? '')
}

function normalizeLogEntry(payload = {}, fallbackLevel = 'INFO') {
  if (typeof payload === 'string') {
    return {
      level: normalizeLogLevel(fallbackLevel),
      timestamp: null,
      context: {},
      message: payload,
      details: {},
      fatal: undefined,
      formatted: formatLogEntry(payload)
    }
  }

  if (!payload || typeof payload !== 'object') {
    const rendered = String(payload ?? '')
    return {
      level: normalizeLogLevel(fallbackLevel),
      timestamp: null,
      context: {},
      message: rendered,
      details: {},
      fatal: undefined,
      formatted: formatLogEntry(rendered)
    }
  }

  const level = normalizeLogLevel(payload.level || fallbackLevel)
  const timestamp = payload.timestamp ? String(payload.timestamp) : null
  const context = payload.context && typeof payload.context === 'object' && !Array.isArray(payload.context)
    ? payload.context
    : {}
  const message = payload.message ? String(payload.message) : ''
  const details = payload.details && typeof payload.details === 'object' && !Array.isArray(payload.details)
    ? payload.details
    : {}

  return {
    ...payload,
    level,
    timestamp,
    context,
    message,
    details,
    fatal: payload.fatal,
    formatted: payload.formatted || formatLogEntry({
      ...payload,
      level,
      timestamp,
      context,
      message
    })
  }
}

export const useTranslateStore = defineStore('translate', () => {
  const config = ref(createDefaultConfig())
  const currentTaskId = ref(null)
  const taskStatus = ref(null)
  const items = ref([])
  const progress = ref(createDefaultProgress())
  const logs = ref([])
  const loading = ref(false)
  const error = ref(null)
  const streaming = ref(false)
  const streamMessage = ref('')
  const latestDonePayload = ref(null)

  let streamAbortController = null

  const isRunning = computed(() => {
    const status = taskStatus.value?.status
    return streaming.value || ['pending', 'running', 'configuring', 'extracting', 'translating', 'assembling'].includes(status)
  })

  const progressPercent = computed(() => {
    if (progress.value.total_items === 0) return 0
    return Math.round((progress.value.completed_items / progress.value.total_items) * 100)
  })

  function appendLog(entry) {
    const fallbackLevel = typeof entry === 'object' && entry !== null
      ? entry.level || entry.data?.level || 'INFO'
      : 'INFO'
    logs.value.push(normalizeLogEntry(entry, fallbackLevel))
  }

  function appendLocalLog(level, message, context = {}, details = {}) {
    appendLog({
      level,
      timestamp: new Date().toISOString(),
      context,
      message,
      details
    })
  }

  function updateProgressFromData(stage, data = {}) {
    progress.value = {
      ...progress.value,
      stage: stage || progress.value.stage,
      total_items: data.total ?? data.total_items ?? progress.value.total_items,
      completed_items: data.current ?? data.completed_items ?? progress.value.completed_items,
      current_file: data.current_file ?? progress.value.current_file,
      tokens_consumed: data.tokens_consumed ?? progress.value.tokens_consumed,
      estimated_cost: data.cost ?? data.estimated_cost ?? progress.value.estimated_cost,
      elapsed_seconds: data.elapsed_seconds ?? progress.value.elapsed_seconds,
      failed_items: data.failed_items ?? progress.value.failed_items,
      failed_batches: data.failed_batches ?? progress.value.failed_batches,
      errors: Array.isArray(data.errors) ? data.errors : progress.value.errors
    }
  }

  function applyProgressEvent(event) {
    const { stage, data = {} } = event || {}

    if (data.task_id != null) {
      currentTaskId.value = data.task_id
    }

    updateProgressFromData(stage, data)

    if (data.message) {
      streamMessage.value = data.message
    }

    if (stage === 'paused') {
      taskStatus.value = { ...(taskStatus.value || {}), status: 'paused', stage }
      return
    }

    if (stage === 'cancelled') {
      taskStatus.value = { ...(taskStatus.value || {}), status: 'cancelled', stage }
      return
    }

    if (['started', 'extracting', 'translating', 'assembling'].includes(stage)) {
      taskStatus.value = {
        ...(taskStatus.value || {}),
        status: stage === 'started' ? 'pending' : stage,
        stage
      }
    }
  }

  function handleLogEvent(event) {
    appendLog(event?.data ?? event ?? '')
  }

  function handleErrorEvent(event) {
    const payload = event?.data || {}
    appendLog({ ...payload, level: payload.level || 'ERROR' })

    if (payload.fatal === false) {
      return
    }

    error.value = payload.message || '翻译过程中发生错误'
    taskStatus.value = {
      ...(taskStatus.value || {}),
      status: 'failed',
      stage: event?.stage || progress.value.stage,
      error: payload.message || '翻译过程中发生错误'
    }
    streaming.value = false
    streamAbortController = null
    loading.value = false
  }

  function handleDoneEvent(event) {
    const { data = {}, stage } = event || {}
    latestDonePayload.value = data

    if (data.task_id != null) {
      currentTaskId.value = data.task_id
    }

    const isCancelled = stage === 'cancelled' || data.status === 'cancelled'

    streaming.value = false
    streamAbortController = null
    loading.value = false

    progress.value = {
      ...progress.value,
      stage: isCancelled ? 'cancelled' : 'complete',
      total_items: data.total_items ?? progress.value.total_items,
      completed_items: data.completed_items ?? data.total_items ?? progress.value.completed_items,
      tokens_consumed: data.tokens_consumed ?? progress.value.tokens_consumed,
      estimated_cost: data.cost ?? progress.value.estimated_cost,
      failed_items: data.failed_items_count ?? progress.value.failed_items,
      failed_batches: data.failed_batches_count ?? progress.value.failed_batches,
      errors: Array.isArray(data.errors) ? data.errors : progress.value.errors
    }

    if (isCancelled) {
      taskStatus.value = {
        ...(taskStatus.value || {}),
        status: 'cancelled',
        task_id: data.task_id
      }
      streamMessage.value = '翻译已取消'
      return
    }

    taskStatus.value = {
      ...(taskStatus.value || {}),
      status: data.status || 'ready_to_apply',
      task_id: data.task_id
    }
    streamMessage.value = '翻译完成'
  }

  function handleTransportError(message) {
    const errorMessage = message || '翻译过程中发生错误'
    appendLocalLog('ERROR', errorMessage, { task: currentTaskId.value || '-' })
    error.value = errorMessage
    taskStatus.value = { ...(taskStatus.value || {}), status: 'failed', error: errorMessage }
    streaming.value = false
    streamAbortController = null
    loading.value = false
  }

  async function saveConfig(data) {
    error.value = null
    try {
      const normalized = {
        ...data,
        batch_retry_limit: normalizeRetryLimit(data?.batch_retry_limit)
      }
      const res = await saveTranslateConfig(normalized)
      config.value = { ...config.value, ...normalized }
      return res.data || res
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '保存配置失败'
    }
  }

  async function startTranslation(modpackVersionId, localPath, translateConfig = null, onStreamReady = null) {
    error.value = null
    loading.value = true
    streaming.value = true
    streamMessage.value = '正在启动翻译...'
    items.value = []
    logs.value = []
    latestDonePayload.value = null
    taskStatus.value = { status: 'pending' }
    progress.value = createDefaultProgress()
    currentTaskId.value = null

    const payload = {
      modpack_version_id: modpackVersionId,
      local_path: localPath
    }
    if (translateConfig) {
      payload.config = {
        ...translateConfig,
        batch_retry_limit: normalizeRetryLimit(translateConfig.batch_retry_limit)
      }
    }

    streamAbortController = new AbortController()
    let streamReady = false

    await startTranslationStream(payload, {
      onProgress(event) {
        applyProgressEvent(event)

        if (!streamReady) {
          streamReady = true
          loading.value = false
          if (onStreamReady) onStreamReady()
        }
      },
      onLog(event) {
        handleLogEvent(event)
      },
      onErrorEvent(event) {
        handleErrorEvent(event)
      },
      onDone(event) {
        handleDoneEvent(event)
      },
      onTransportError(message) {
        handleTransportError(message)
      }
    }, streamAbortController.signal)
  }

  async function startTranslationLegacy(modpackVersionId, localPath, translateConfig = null) {
    error.value = null
    loading.value = true
    try {
      const payload = {
        modpack_version_id: modpackVersionId,
        local_path: localPath
      }
      if (translateConfig) {
        payload.config = {
          ...translateConfig,
          batch_retry_limit: normalizeRetryLimit(translateConfig.batch_retry_limit)
        }
      }
      const res = await startTranslationApi(payload)
      const data = res.data || res
      currentTaskId.value = data.task_id
      taskStatus.value = data
      progress.value = { ...progress.value, stage: 'started' }
      pollStatus(data.task_id)
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '启动翻译失败'
    } finally {
      loading.value = false
    }
  }

  function pollStatus(taskId) {
    stopPolling()
    const fetch = async () => {
      try {
        const res = await getTranslateStatus(taskId)
        const data = res.data || res
        taskStatus.value = data
        progress.value = {
          ...progress.value,
          stage: data.stage || progress.value.stage,
          total_items: data.total_items || 0,
          completed_items: data.completed_items || 0,
          current_file: data.current_file || progress.value.current_file,
          tokens_consumed: data.tokens_consumed || 0,
          estimated_cost: data.estimated_cost || data.cost || 0,
          elapsed_seconds: data.elapsed_seconds || progress.value.elapsed_seconds
        }
        if (['completed', 'failed', 'cancelled', 'ready_to_apply'].includes(data.status)) {
          stopPolling()
        }
      } catch (e) {
        error.value = e.response?.data?.detail || e.message || '获取状态失败'
        stopPolling()
      }
    }
    fetch()
    pollingTimer = setInterval(fetch, 2000)
  }

  function stopPolling() {
    if (pollingTimer) {
      clearInterval(pollingTimer)
      pollingTimer = null
    }
  }

  async function pauseTranslation() {
    if (!currentTaskId.value) return
    error.value = null
    try {
      const res = await pauseTranslationApi(currentTaskId.value)
      const data = res.data || res
      const statusData = data.data || data
      taskStatus.value = statusData
      if (streaming.value) {
        streamMessage.value = '翻译已暂停，等待恢复...'
      }
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '暂停翻译失败'
    }
  }

  async function resumeTranslation() {
    if (!currentTaskId.value) return
    error.value = null
    try {
      const res = await resumeTranslationApi(currentTaskId.value)
      const data = res.data || res
      const statusData = data.data || data
      taskStatus.value = statusData
      if (streaming.value) {
        streamMessage.value = '翻译已恢复...'
      }
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '继续翻译失败'
    }
  }

  async function cancelTranslation() {
    if (!currentTaskId.value) return
    error.value = null
    try {
      const res = await cancelTranslationApi(currentTaskId.value)
      const data = res.data || res
      const statusData = data.data || data
      taskStatus.value = statusData
      if (streamAbortController) {
        streamAbortController.abort()
        streamAbortController = null
      }
      streaming.value = false
      progress.value = { ...progress.value, stage: 'cancelled' }
      streamMessage.value = '翻译已取消'
      appendLocalLog('WARN', '翻译任务已由用户取消', { task: currentTaskId.value || '-' })
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '取消翻译失败'
    } finally {
      stopPolling()
    }
  }

  async function loadItems(taskId, offset = 0, limit = 50) {
    error.value = null
    try {
      const res = await getTranslateItems(taskId, offset, limit)
      const data = res.data || res
      items.value = data.items || data.results || []
      return data
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '加载翻译项失败'
    }
  }

  function reset() {
    stopPolling()
    if (streamAbortController) {
      streamAbortController.abort()
      streamAbortController = null
    }
    config.value = {
      ...createDefaultConfig(),
      ai_model: 'gpt-4o',
      batch_size: 20,
      concurrency: 3,
      batch_retry_limit: DEFAULT_BATCH_RETRY_LIMIT
    }
    currentTaskId.value = null
    taskStatus.value = null
    items.value = []
    progress.value = createDefaultProgress()
    logs.value = []
    latestDonePayload.value = null
    loading.value = false
    error.value = null
    streaming.value = false
    streamMessage.value = ''
  }

  return {
    config,
    currentTaskId,
    taskStatus,
    items,
    progress,
    logs,
    loading,
    error,
    streaming,
    streamMessage,
    latestDonePayload,
    isRunning,
    progressPercent,
    appendLog,
    appendLocalLog,
    applyProgressEvent,
    handleLogEvent,
    handleErrorEvent,
    handleDoneEvent,
    handleTransportError,
    saveConfig,
    startTranslation,
    startTranslationLegacy,
    pollStatus,
    stopPolling,
    pauseTranslation,
    resumeTranslation,
    cancelTranslation,
    loadItems,
    reset
  }
})
