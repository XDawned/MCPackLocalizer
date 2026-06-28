import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import apiClient from '@/api'

export const GLOBAL_NAV_ITEMS = [
  {
    key: 'home',
    label: '首页',
    route: '/',
    description: '回到桌面工作台'
  },
  {
    key: 'search',
    label: '检索整合包',
    route: '/search',
    description: '从平台搜索并进入本地化流程'
  },
  {
    key: 'localImport',
    label: '本地导入',
    route: '/local-import',
    description: '扫描本地整合包并准备翻译'
  },
  {
    key: 'history',
    label: '处理历史',
    route: '/history',
    description: '查看并恢复先前处理记录'
  },
  {
    key: 'glossary',
    label: '术语库',
    route: '/glossary',
    description: '维护术语与翻译一致性'
  }
]

export const WORKFLOW_STEPS = [
  {
    id: 1,
    key: 'package_retrieval',
    label: '检索整合包',
    icon: 'search',
    route: '/search',
    description: '选择要本地化的整合包'
  },
  {
    id: 2,
    key: 'localization_config',
    label: '本地化配置',
    icon: 'setting',
    route: '/l10n-config',
    description: '配置翻译参数与处理范围'
  },
  {
    id: 3,
    key: 'ai_translation',
    label: 'AI 翻译工作流',
    icon: 'language',
    route: '/translating',
    description: '执行翻译并跟踪实时进度'
  },
  {
    id: 4,
    key: 'file_application',
    label: '汉化文件应用',
    icon: 'cube',
    route: '/apply',
    description: '将翻译结果应用到整合包'
  },
  {
    id: 5,
    key: 'effect_verification',
    label: '效果验证',
    icon: 'check',
    route: '/translation-review',
    description: '验证结果并继续后续处理'
  }
]

export const AUXILIARY_STEPS = [
  {
    id: 6,
    key: 'cache_recording',
    label: '记录缓存',
    icon: 'history',
    route: '/translation-review',
    description: '流程完成后写入可复用缓存'
  },
  {
    id: 7,
    key: 'ai_repair',
    label: 'AI Agent 修复',
    icon: 'globe',
    route: '/translation-review',
    description: '翻译存在问题时进入修复分支'
  },
  {
    id: 8,
    key: 'manual_intervention',
    label: '人工介入',
    icon: 'setting',
    route: '/translation-review',
    description: 'AI 修复失败后人工处理'
  }
]

const ALL_STEPS = [...WORKFLOW_STEPS, ...AUXILIARY_STEPS]
const STEP_MAP = Object.fromEntries(ALL_STEPS.map(step => [step.id, step]))
const ROUTE_STEP_MAP = Object.fromEntries(WORKFLOW_STEPS.map(step => [step.route, step.id]))
const PAGE_META_MAP = Object.fromEntries([
  ...GLOBAL_NAV_ITEMS,
  ...WORKFLOW_STEPS,
  { key: 'workflow', label: '本地化工作流', route: '/workflow', description: '查看当前任务的逻辑流转状态' },
  { key: 'settingsGeneral', label: '通用设置', route: '/settings/general', description: '维护通用运行配置' },
  { key: 'settingsCache', label: '缓存设置', route: '/settings/cache', description: '查看缓存统计并执行清理' },
  { key: 'settings', label: '系统设置', route: '/settings', description: '统一管理运行配置' },
  { key: 'modpackDetail', label: '整合包详情', route: '/modpack-detail', description: '查看整合包版本与详情' }
].map(item => [item.route, item]))

let pollingTimer = null

function createDefaultStepStatuses() {
  return {
    1: 'pending',
    2: 'blocked',
    3: 'blocked',
    4: 'blocked',
    5: 'blocked',
    6: 'blocked',
    7: 'blocked',
    8: 'blocked'
  }
}

function createEmptyContext() {
  return {
    taskId: null,
    modpackVersionId: null,
    localPath: '',
    scanId: null,
    restoredFromHistory: false,
    recommendedRoute: null
  }
}

function normalizeString(value) {
  if (value === undefined || value === null) return ''
  return String(value).trim()
}

function normalizeTaskId(value) {
  const normalized = normalizeString(value)
  return normalized || null
}

function normalizeLocalPath(value) {
  return normalizeString(value)
}

function normalizeScanId(value) {
  const normalized = normalizeString(value)
  return normalized || null
}

function normalizeModpackVersionId(value) {
  if (value === undefined || value === null || value === '') return null
  return String(value)
}

function compactQuery(query = {}) {
  return Object.fromEntries(
    Object.entries(query).filter(([, value]) => value !== undefined && value !== null && value !== '')
  )
}

function toPlainRouteQuery(query = {}) {
  return {
    taskId: normalizeTaskId(query.taskId),
    modpackVersionId: normalizeModpackVersionId(query.modpackVersionId),
    localPath: normalizeLocalPath(query.localPath),
    scanId: normalizeScanId(query.scanId)
  }
}

export function resolveWorkflowStepByPath(path) {
  return ROUTE_STEP_MAP[path] || null
}

export function isWorkflowPath(path) {
  return Boolean(resolveWorkflowStepByPath(path))
}

export function getPageMetaByPath(path) {
  if (path?.startsWith('/modpack/')) {
    return PAGE_META_MAP['/modpack-detail']
  }
  return PAGE_META_MAP[path] || null
}

function createLinearStepStatuses(activeStep = 1) {
  const next = createDefaultStepStatuses()
  const normalizedStep = Math.max(1, Math.min(5, Number(activeStep || 1)))

  for (let step = 1; step <= 5; step += 1) {
    if (step < normalizedStep) {
      next[step] = 'completed'
    } else if (step === normalizedStep) {
      next[step] = 'active'
    } else if (step === normalizedStep + 1) {
      next[step] = 'pending'
    }
  }

  return next
}

function deriveStepFromStatus(status, fallback = 1) {
  const normalized = normalizeString(status).toLowerCase()

  if (['configuring', 'pending'].includes(normalized)) return 2
  if (['extracting', 'translating', 'assembling', 'paused', 'cancelled'].includes(normalized)) return 3
  if (normalized === 'ready_to_apply') return 4
  if (['applied', 'completed', 'verified', 'needs_fix', 'fixing', 'failed'].includes(normalized)) return 5
  return Math.max(1, Math.min(5, Number(fallback || 1)))
}

function deriveStatusesFromTaskStatus(status, fallbackStep = 1) {
  const normalized = normalizeString(status).toLowerCase()
  const activeStep = deriveStepFromStatus(normalized, fallbackStep)
  const next = createLinearStepStatuses(activeStep)

  if (normalized === 'applied') {
    next[4] = 'completed'
    next[5] = 'active'
  }

  if (['completed', 'verified'].includes(normalized)) {
    next[5] = 'completed'
    next[6] = 'completed'
  }

  if (['needs_fix', 'fixing'].includes(normalized)) {
    next[5] = 'completed'
    next[7] = 'active'
  }

  if (normalized === 'failed') {
    next[5] = 'completed'
    next[7] = 'failed'
    next[8] = 'active'
  }

  return next
}

export const useWorkflowStore = defineStore('workflow', () => {
  const currentTaskId = ref(null)
  const currentStep = ref(1)
  const stepStatuses = ref(createDefaultStepStatuses())
  const branchTaken = ref(null)
  const repairOutcome = ref(null)
  const loading = ref(false)
  const error = ref(null)
  const taskStatus = ref(null)
  const routeContext = ref(createEmptyContext())

  const currentStepInfo = computed(() => STEP_MAP[currentStep.value] || WORKFLOW_STEPS[0])
  const globalNavigation = computed(() => GLOBAL_NAV_ITEMS)
  const workflowSteps = computed(() => WORKFLOW_STEPS)
  const hasPackContext = computed(() => Boolean(routeContext.value.localPath))
  const hasTaskContext = computed(() => Boolean(currentTaskId.value || routeContext.value.taskId))

  const progressPercent = computed(() => {
    const completedCount = Object.values(stepStatuses.value).filter(status => status === 'completed').length
    return Math.round((completedCount / ALL_STEPS.length) * 100)
  })

  const activeSteps = computed(() => {
    return ALL_STEPS
      .filter(step => stepStatuses.value[step.id] !== 'blocked')
      .map(step => step.id)
  })

  const canAdvance = computed(() => {
    const nextStep = currentStep.value + 1
    if (!STEP_MAP[nextStep]) return false
    if (stepStatuses.value[currentStep.value] !== 'completed') return false
    return isStepAccessible(nextStep)
  })

  const isComplete = computed(() => {
    const normalized = normalizeString(taskStatus.value?.status).toLowerCase()
    return ['completed', 'verified'].includes(normalized) || stepStatuses.value[6] === 'completed'
  })

  const workflowStateLabel = computed(() => {
    const step = currentStep.value
    const status = stepStatuses.value[step]
    const info = STEP_MAP[step]
    if (!info) return '未知状态'

    if (status === 'completed') return `${info.label} - 已完成`
    if (status === 'active') return `${info.label} - 进行中`
    if (status === 'failed') return `${info.label} - 失败`
    if (status === 'pending') return `准备${info.label}`
    if (status === 'blocked') {
      const previousStep = resolvePreviousStep(step)
      if (previousStep) return `等待完成: ${STEP_MAP[previousStep]?.label || '上一步'}`
      return '等待开始'
    }
    if (status === 'skipped') return `${info.label} - 已跳过`
    return info.label
  })

  function updateRouteContext(patch = {}) {
    const next = {
      ...routeContext.value,
      ...(patch.taskId !== undefined ? { taskId: normalizeTaskId(patch.taskId) } : {}),
      ...(patch.modpackVersionId !== undefined ? { modpackVersionId: normalizeModpackVersionId(patch.modpackVersionId) } : {}),
      ...(patch.localPath !== undefined ? { localPath: normalizeLocalPath(patch.localPath) } : {}),
      ...(patch.scanId !== undefined ? { scanId: normalizeScanId(patch.scanId) } : {}),
      ...(patch.restoredFromHistory !== undefined ? { restoredFromHistory: Boolean(patch.restoredFromHistory) } : {}),
      ...(patch.recommendedRoute !== undefined ? { recommendedRoute: patch.recommendedRoute || null } : {})
    }

    routeContext.value = next
    currentTaskId.value = next.taskId || currentTaskId.value || null
  }

  function syncRouteContext(routeLike = {}) {
    const query = toPlainRouteQuery(routeLike.query || {})
    updateRouteContext(query)

    const stepId = resolveWorkflowStepByPath(routeLike.path)
    if (stepId) {
      currentStep.value = stepId
      if (!taskStatus.value?.status) {
        stepStatuses.value = deriveStatusesFromTaskStatus(null, stepId)
      }
    }
  }

  function getStepQuery(stepId, overrides = {}) {
    const merged = {
      ...routeContext.value,
      taskId: currentTaskId.value || routeContext.value.taskId,
      ...toPlainRouteQuery(overrides)
    }

    const query = {}

    if (stepId >= 2 && merged.localPath) {
      query.localPath = merged.localPath
    }

    if (stepId >= 2 && merged.modpackVersionId !== null) {
      query.modpackVersionId = merged.modpackVersionId
    }

    if ([2, 3].includes(stepId) && merged.scanId) {
      query.scanId = merged.scanId
    }

    if (stepId >= 3 && merged.taskId) {
      query.taskId = merged.taskId
    }

    return compactQuery(query)
  }

  function getStepLocation(stepId, overrides = {}) {
    const step = STEP_MAP[stepId]
    if (!step) return { path: '/workflow' }
    return {
      path: step.route,
      query: getStepQuery(stepId, overrides)
    }
  }

  function resolvePreviousStep(stepId = currentStep.value) {
    if (stepId === 8) return 7
    if (stepId === 7 || stepId === 6) return 5
    if (stepId <= 1) return null
    return Math.min(stepId - 1, 5)
  }

  function getBackLocation(stepId = currentStep.value) {
    const previousStep = resolvePreviousStep(stepId)
    if (!previousStep) {
      return { path: '/search' }
    }
    return getStepLocation(previousStep)
  }

  function resolveAccessContext(query = null) {
    const normalizedQuery = query ? toPlainRouteQuery(query) : {}
    return {
      taskId: normalizedQuery.taskId || currentTaskId.value || routeContext.value.taskId,
      modpackVersionId: normalizedQuery.modpackVersionId ?? routeContext.value.modpackVersionId,
      localPath: normalizedQuery.localPath || routeContext.value.localPath,
      scanId: normalizedQuery.scanId || routeContext.value.scanId
    }
  }

  function isStepAccessible(stepId, query = null) {
    const context = resolveAccessContext(query)

    if (stepId === 1) return true
    if (stepId === 2) return Boolean(context.localPath)
    if ([3, 4, 5].includes(stepId)) return Boolean(context.taskId)
    if (stepId === 6) {
      return stepStatuses.value[5] === 'completed' && branchTaken.value === 'success'
    }
    if (stepId === 7) {
      return stepStatuses.value[5] === 'completed' && branchTaken.value === 'repair'
    }
    if (stepId === 8) {
      return stepStatuses.value[7] === 'failed'
    }
    return false
  }

  function validateStepAccess(stepId, query = null) {
    const context = resolveAccessContext(query)

    if (stepId === 1) {
      return { allowed: true }
    }

    if (stepId === 2 && !context.localPath) {
      return {
        allowed: false,
        redirect: { path: '/search' }
      }
    }

    if ([3, 4, 5].includes(stepId) && !context.taskId) {
      if (context.localPath) {
        return {
          allowed: false,
          redirect: getStepLocation(2, context)
        }
      }

      return {
        allowed: false,
        redirect: { path: '/search' }
      }
    }

    return { allowed: true }
  }

  function applyBackendStepStatuses(backendStatuses) {
    if (!backendStatuses || typeof backendStatuses !== 'object') return
    const next = { ...stepStatuses.value }
    for (let step = 1; step <= ALL_STEPS.length; step += 1) {
      if (backendStatuses[step] !== undefined) {
        next[step] = backendStatuses[step]
      }
    }
    stepStatuses.value = next
  }

  function applyTaskSnapshot(snapshot = {}, preferredStep = null) {
    taskStatus.value = snapshot
    const nextStep = deriveStepFromStatus(snapshot?.status, preferredStep ?? currentStep.value)
    currentStep.value = nextStep
    stepStatuses.value = deriveStatusesFromTaskStatus(snapshot?.status, nextStep)

    if (['completed', 'verified'].includes(normalizeString(snapshot?.status).toLowerCase())) {
      branchTaken.value = 'success'
      repairOutcome.value = 'success'
    }
  }

  async function initWorkflow(taskId) {
    if (!taskId) {
      reset()
      return
    }
    currentTaskId.value = normalizeTaskId(taskId)
    updateRouteContext({ taskId })
    loading.value = true
    error.value = null
    try {
      const data = await apiClient.get(`/workflow/${currentTaskId.value}`)
      taskStatus.value = data
      if (data.current_step !== undefined) {
        currentStep.value = data.current_step
      }
      if (data.step_statuses) {
        applyBackendStepStatuses(data.step_statuses)
      } else {
        applyTaskSnapshot(data, data.current_step)
      }
      if (data.branch_taken !== undefined) {
        branchTaken.value = data.branch_taken
      }
      if (data.repair_outcome !== undefined) {
        repairOutcome.value = data.repair_outcome
      }
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '获取工作流状态失败'
    } finally {
      loading.value = false
    }
  }

  function startWorkflow(modpackVersionId = null, localPath = '', scanId = null) {
    currentTaskId.value = null
    taskStatus.value = null
    updateRouteContext({
      taskId: null,
      modpackVersionId,
      localPath,
      scanId,
      restoredFromHistory: false,
      recommendedRoute: null
    })
    currentStep.value = localPath ? 2 : 1
    stepStatuses.value = createLinearStepStatuses(currentStep.value)
    branchTaken.value = null
    repairOutcome.value = null
  }

  async function advanceToStep(stepId) {
    if (!isStepAccessible(stepId)) {
      error.value = '无法访问该步骤'
      return
    }
    if (!currentTaskId.value) {
      error.value = '没有活动任务'
      return
    }
    loading.value = true
    error.value = null
    try {
      const data = await apiClient.post(`/workflow/${currentTaskId.value}/advance`, { next_stage: stepId })
      taskStatus.value = data
      if (data.current_step !== undefined) {
        currentStep.value = data.current_step
      }
      if (data.step_statuses) {
        applyBackendStepStatuses(data.step_statuses)
      }
      if (data.branch_taken !== undefined) {
        branchTaken.value = data.branch_taken
      }
      if (data.repair_outcome !== undefined) {
        repairOutcome.value = data.repair_outcome
      }
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '推进工作流失败'
    } finally {
      loading.value = false
    }
  }

  async function completeCurrentStep(success = true) {
    if (!currentTaskId.value) {
      error.value = '没有活动任务'
      return
    }

    const step = currentStep.value
    loading.value = true
    error.value = null

    try {
      const data = await apiClient.post(
        `/workflow/${currentTaskId.value}/complete/${step}`,
        null,
        { params: { success } }
      )
      taskStatus.value = data

      if (step === 5) {
        if (success) {
          stepStatuses.value[5] = 'completed'
          stepStatuses.value[6] = 'active'
          stepStatuses.value[7] = 'blocked'
          stepStatuses.value[8] = 'blocked'
          branchTaken.value = 'success'
        } else {
          stepStatuses.value[5] = 'completed'
          stepStatuses.value[6] = 'blocked'
          stepStatuses.value[7] = 'active'
          stepStatuses.value[8] = 'blocked'
          branchTaken.value = 'repair'
        }
      } else if (step === 7) {
        if (success) {
          stepStatuses.value[7] = 'completed'
          stepStatuses.value[6] = 'active'
          repairOutcome.value = 'success'
        } else {
          stepStatuses.value[7] = 'failed'
          stepStatuses.value[8] = 'active'
          repairOutcome.value = 'failed'
        }
      }

      if (data.step_statuses) {
        applyBackendStepStatuses(data.step_statuses)
      }
      if (data.current_step !== undefined) {
        currentStep.value = data.current_step
      }
      if (data.branch_taken !== undefined) {
        branchTaken.value = data.branch_taken
      }
      if (data.repair_outcome !== undefined) {
        repairOutcome.value = data.repair_outcome
      }
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '完成步骤失败'
    } finally {
      loading.value = false
    }
  }

  function goToStep(stepId, overrides = {}) {
    if (!isStepAccessible(stepId, overrides)) return null
    currentStep.value = stepId
    return getStepLocation(stepId, overrides)
  }

  async function fetchWorkflowState() {
    if (!currentTaskId.value) return
    loading.value = true
    error.value = null
    try {
      const data = await apiClient.get(`/workflow/${currentTaskId.value}`)
      taskStatus.value = data
      if (data.current_step !== undefined) {
        currentStep.value = data.current_step
      }
      if (data.step_statuses) {
        applyBackendStepStatuses(data.step_statuses)
      } else {
        applyTaskSnapshot(data, currentStep.value)
      }
      if (data.branch_taken !== undefined) {
        branchTaken.value = data.branch_taken
      }
      if (data.repair_outcome !== undefined) {
        repairOutcome.value = data.repair_outcome
      }
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '获取工作流状态失败'
    } finally {
      loading.value = false
    }
  }

  function hydrateFromHistory(restoreContext = {}) {
    const task = restoreContext.task || {}
    const config = restoreContext.config || {}
    const scanResult = restoreContext.scan_result || {}

    updateRouteContext({
      taskId: task.task_id || restoreContext.route_query?.taskId,
      modpackVersionId: restoreContext.route_query?.modpackVersionId,
      localPath: restoreContext.route_query?.localPath || config.local_path || routeContext.value.localPath,
      scanId: config.scan_id || scanResult.scan_id || routeContext.value.scanId,
      restoredFromHistory: true,
      recommendedRoute: restoreContext.recommended_route || null
    })

    currentTaskId.value = normalizeTaskId(task.task_id || currentTaskId.value)
    currentStep.value = deriveStepFromStatus(task.status, restoreContext.current_step || 1)
    stepStatuses.value = deriveStatusesFromTaskStatus(task.status, currentStep.value)
    taskStatus.value = task

    if (['completed', 'verified'].includes(normalizeString(task.status).toLowerCase())) {
      branchTaken.value = 'success'
      repairOutcome.value = 'success'
    } else {
      branchTaken.value = null
      repairOutcome.value = null
    }
  }

  function stopPolling() {
    if (pollingTimer) {
      clearInterval(pollingTimer)
      pollingTimer = null
    }
  }

  function reset() {
    stopPolling()
    currentTaskId.value = null
    currentStep.value = 1
    stepStatuses.value = createDefaultStepStatuses()
    branchTaken.value = null
    repairOutcome.value = null
    loading.value = false
    error.value = null
    taskStatus.value = null
    routeContext.value = createEmptyContext()
  }

  return {
    currentTaskId,
    currentStep,
    stepStatuses,
    branchTaken,
    repairOutcome,
    loading,
    error,
    taskStatus,
    routeContext,
    globalNavigation,
    workflowSteps,
    hasPackContext,
    hasTaskContext,
    currentStepInfo,
    isStepAccessible,
    validateStepAccess,
    progressPercent,
    activeSteps,
    canAdvance,
    isComplete,
    workflowStateLabel,
    syncRouteContext,
    updateRouteContext,
    getStepQuery,
    getStepLocation,
    getBackLocation,
    resolvePreviousStep,
    applyTaskSnapshot,
    initWorkflow,
    startWorkflow,
    advanceToStep,
    completeCurrentStep,
    goToStep,
    fetchWorkflowState,
    hydrateFromHistory,
    stopPolling,
    reset
  }
})
