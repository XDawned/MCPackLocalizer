<script setup>
import {reactive, ref, computed, onMounted, watch, inject} from 'vue'
import {useRoute, useRouter} from 'vue-router'
import {
  ElButton,
  ElInput,
  ElSwitch,
  ElSelect,
  ElOption,
  ElInputNumber,
  ElAlert,
  ElCollapse,
  ElCollapseItem,
  ElMessage
} from 'element-plus'
import {useTranslateStore} from '@/stores/translate'
import {useSettingsStore} from '@/stores/settings'
import {useLocalPackStore} from '@/stores/localPack'
import {useWorkflowStore} from '@/stores/workflow'
import TranslatableAreas from '@/components/common/TranslatableAreas.vue'
import {
  KUBEJS_AREA_TYPES,
  asBooleanSetting,
  getAreaMeta,
  getAreaSelectionSummary
} from '@/utils/localizationDelivery'

const route = useRoute()
const router = useRouter()
const translateStore = useTranslateStore()
const settingsStore = useSettingsStore()
const localPackStore = useLocalPackStore()
const workflowStore = useWorkflowStore()
const openSettings = inject('openSettings', null)

// ==================== 待翻译文本预览 ====================
const scanId = computed(() => route.query.scanId || null)
const previewLoading = ref(false)
const previewError = ref(null)
const previewItems = ref([])
const previewTotal = ref(0)
const previewExpanded = ref(false)
const PREVIEW_LIMIT = 50

// ==================== 翻译启动状态与错误 ====================
const translationStarting = ref(false)
const translationError = ref(null)

const displayItems = computed(() => {
  if (previewExpanded.value) return previewItems.value
  return previewItems.value.slice(0, PREVIEW_LIMIT)
})

async function loadPreview() {
  if (!scanId.value) return
  previewLoading.value = true
  previewError.value = null
  try {
    const data = await localPackStore.extract(scanId.value)
    if (data) {
      previewItems.value = data.items || []
      previewTotal.value = data.total_entries || previewItems.value.length
    } else {
      previewItems.value = []
      previewTotal.value = 0
      previewError.value = localPackStore.error || '加载预览失败'
    }
  } catch (e) {
    previewError.value = e.response?.data?.detail || e.message || '加载预览失败'
  } finally {
    previewLoading.value = false
  }
}

const activeCollapse = ref([])
const localConfig = reactive({
  ...translateStore.config,
  custom_prompt: translateStore.config.custom_prompt || '',
  batch_retry_limit: normalizeRetryLimit(translateStore.config.batch_retry_limit)
})
const deliverySettingsSaving = ref(false)

const currentScanResult = computed(() => {
  if (!scanId.value) return null
  return localPackStore.scanResult?.scan_id === scanId.value ? localPackStore.scanResult : null
})

const scanAreaSelectionSummary = computed(() => {
  return getAreaSelectionSummary(localPackStore.selectableAreas, localPackStore.selectedAreas)
})

const scanAreaBadges = computed(() => {
  return localPackStore.selectableAreas.map(area => ({
    type: area.type,
    label: area.label || getAreaMeta(area.type).label,
    count: Number(area.count || 0)
  }))
})

const kubejsAvailableTypes = computed(() => {
  return localPackStore.selectableAreas
    .map(area => area.type)
    .filter(type => KUBEJS_AREA_TYPES.includes(type))
})

const hasKubejsAreas = computed(() => kubejsAvailableTypes.value.length > 0)
const hasFtbLangArea = computed(() => localPackStore.selectableAreas.some(area => area.type === 'ftbquests_lang'))
const hasFtbQuestSourceArea = computed(() => localPackStore.selectableAreas.some(area => area.type === 'ftb_quests'))
const hasFtbPriorityChoice = computed(() => hasFtbLangArea.value && hasFtbQuestSourceArea.value)
const includeI18nUpdateMod = computed(() => asBooleanSetting(settingsStore.settings?.include_i18n_update_mod, false))

function setAreaSelection(types = [], enabled = true) {
  const available = localPackStore.selectableAreas.map(area => area.type)
  const nextSelected = new Set(localPackStore.selectedAreas)

  types.forEach(type => {
    if (enabled) {
      nextSelected.add(type)
    } else {
      nextSelected.delete(type)
    }
  })

  localPackStore.selectedAreas = available.filter(type => nextSelected.has(type))
}

const includeKubejsAreas = computed({
  get() {
    if (!hasKubejsAreas.value) return false
    return kubejsAvailableTypes.value.every(type => localPackStore.selectedAreas.includes(type))
  },
  set(value) {
    setAreaSelection(kubejsAvailableTypes.value, value)
  }
})

const preferFtbLangTree = computed({
  get() {
    if (!hasFtbPriorityChoice.value) return false
    return localPackStore.selectedAreas.includes('ftbquests_lang') && !localPackStore.selectedAreas.includes('ftb_quests')
  },
  set(value) {
    if (!hasFtbPriorityChoice.value) return

    if (value) {
      setAreaSelection(['ftbquests_lang'], true)
      setAreaSelection(['ftb_quests'], false)
      return
    }

    setAreaSelection(['ftb_quests'], true)
    setAreaSelection(['ftbquests_lang'], false)
  }
})

async function ensureScanAreasLoaded() {
  if (!scanId.value) return
  if (localPackStore.selectableAreas.length > 0) return
  await localPackStore.loadAreas(scanId.value)
}

async function handleToggleI18nUpdateMod(value) {
  deliverySettingsSaving.value = true
  try {
    await settingsStore.saveSettings({
      include_i18n_update_mod: value ? 'true' : 'false'
    })
    ElMessage.success(value ? '已启用 I18nUpdateMod 随补丁附带' : '已关闭 I18nUpdateMod 随补丁附带')
  } catch (_) {
    // store 已处理错误
  } finally {
    deliverySettingsSaving.value = false
  }
}

function normalizeRetryLimit(value, fallback = 3) {
  const parsed = Number.parseInt(String(value ?? fallback), 10)
  if (Number.isNaN(parsed)) return fallback
  return Math.min(3, Math.max(0, parsed))
}

function getPersistedRetryLimit() {
  return normalizeRetryLimit(settingsStore.settings?.translate_batch_retry_limit, localConfig.batch_retry_limit)
}

function syncRetryLimitFromSettings() {
  const retryLimit = getPersistedRetryLimit()
  localConfig.batch_retry_limit = retryLimit
  translateStore.config.batch_retry_limit = retryLimit
}

// ==================== Provider 选择与覆写 ====================

const selectedProviderId = ref(null)
const overrideEnabled = ref(false)

// 覆写参数
const overrideConfig = reactive({
  api_base: '',
  api_key: '',
  default_model: ''
})

// 模型输入方式：下拉选择 or 手工输入
const modelInputMode = ref('select') // 'select' | 'manual'
const selectedModelFromList = ref('')
const manualModelInput = ref('')

// 模型列表
const modelList = ref([])
const loadingModels = ref(false)
const modelsError = ref(null)

// 测试连接
const testingConnection = ref(false)
const testResult = ref(null)

// 已启用的 provider 列表
const enabledProviders = computed(() => settingsStore.aiProviders.filter(p => p.is_enabled))

// 当前选中的 provider 对象
const selectedProvider = computed(() => {
  if (!selectedProviderId.value) return null
  return settingsStore.aiProviders.find(p => p.id === selectedProviderId.value) || null
})

// 最终使用的模型名
const effectiveModel = computed(() => {
  if (overrideEnabled.value && overrideConfig.default_model) {
    return overrideConfig.default_model
  }
  if (modelInputMode.value === 'select' && selectedModelFromList.value) {
    return selectedModelFromList.value
  }
  if (modelInputMode.value === 'manual' && manualModelInput.value) {
    return manualModelInput.value
  }
  return selectedProvider.value?.default_model || ''
})

// provider 描述
const providerDescriptions = {
  openai: 'OpenAI 通用接口',
  anthropic: 'Anthropic Claude — 超强编码能力',
  deepseek: 'DeepSeek — 高性价比，中文翻译表现出色',
  qwen: '通义千问 — 阿里巴巴出品，中文理解优秀',
  zhipu: '智谱 GLM — 清华出品，中文能力扎实',
  ollama: 'Ollama 本地模型 — 完全离线，数据安全，需本地部署'
}

const providerDescription = computed(() => {
  if (!selectedProvider.value) return ''
  return providerDescriptions[selectedProvider.value.provider_type] || ''
})

const cacheScopeOptions = [
  {value: 'version', label: '仅当前版本'},
  {value: 'modpack', label: '同一整合包'},
  {value: 'all', label: '所有已缓存'}
]

const canStart = computed(() => {
  const hasModpackVersionId = !!route.query.modpackVersionId
  const hasLocalPath = !!route.query.localPath
  const hasProvider = !!selectedProviderId.value
  return (hasModpackVersionId && hasLocalPath) && hasProvider && !translateStore.loading
})

// ==================== 模型列表拉取 ====================

async function fetchModels() {
  if (!selectedProviderId.value) {
    modelList.value = []
    return
  }
  loadingModels.value = true
  modelsError.value = null
  try {
    const override = overrideEnabled.value ? buildOverride() : null
    const data = await settingsStore.loadAIModels(selectedProviderId.value, override)
    modelList.value = data?.models || []
  } catch (e) {
    modelsError.value = e.response?.data?.detail || e.message || '获取模型列表失败'
    modelList.value = []
  } finally {
    loadingModels.value = false
  }
}

// ==================== 测试连接 ====================

async function handleTestConnection() {
  if (!selectedProviderId.value) {
    ElMessage.warning('请先选择 AI 提供商')
    return
  }
  testingConnection.value = true
  testResult.value = null
  try {
    const override = overrideEnabled.value ? buildOverride() : null
    const model = effectiveModel.value || null
    const result = await settingsStore.testConnection(selectedProviderId.value, override, model)
    testResult.value = result
    if (result.success) {
      ElMessage.success(`连接成功！延迟 ${result.latency_ms ?? '—'}ms${result.model_used ? '，模型: ' + result.model_used : ''}`)
    } else {
      ElMessage.error(`连接失败: ${result.message || '未知错误'}`)
    }
  } catch (e) {
    testResult.value = {success: false, message: e.message || '测试失败'}
  } finally {
    testingConnection.value = false
  }
}

// ==================== 构建 override ====================

function buildOverride() {
  const override = {}
  if (overrideConfig.api_base.trim()) {
    override.api_base = overrideConfig.api_base.trim()
  }
  if (overrideConfig.api_key) {
    override.api_key = overrideConfig.api_key
  }
  if (overrideConfig.default_model.trim()) {
    override.default_model = overrideConfig.default_model.trim()
  }
  return Object.keys(override).length > 0 ? override : null
}

// ==================== Provider 切换处理 ====================

watch(selectedProviderId, (newId) => {
  // 重置覆写和模型
  overrideEnabled.value = false
  overrideConfig.api_base = ''
  overrideConfig.api_key = ''
  overrideConfig.default_model = ''
  selectedModelFromList.value = ''
  manualModelInput.value = ''
  modelList.value = []
  modelsError.value = null
  testResult.value = null

  // 更新 localConfig 中的 ai_provider
  const provider = settingsStore.aiProviders.find(p => p.id === newId)
  if (provider) {
    localConfig.ai_provider = provider.provider_type
    localConfig.ai_model = provider.default_model || ''
    // 拉取模型列表
    fetchModels()
  }
})

// 当覆写开关变化时，重置覆写参数
watch(overrideEnabled, (val) => {
  if (!val) {
    overrideConfig.api_base = ''
    overrideConfig.api_key = ''
    overrideConfig.default_model = ''
  }
  // 重新拉取模型列表（覆写可能影响模型列表）
  if (selectedProviderId.value) {
    fetchModels()
  }
})

// 模型输入方式切换
watch(modelInputMode, (mode) => {
  if (mode === 'select') {
    manualModelInput.value = ''
  } else {
    selectedModelFromList.value = ''
  }
})

watch(
  () => [...localPackStore.selectedAreas],
  () => {
    if (scanId.value && localPackStore.selectableAreas.length > 0) {
      loadPreview()
    }
  },
  { deep: true }
)

// ==================== 启动翻译 ====================

async function handleStartTranslation() {
  if (!selectedProviderId.value) {
    ElMessage.warning('请先选择 AI 提供商')
    return
  }

  translationStarting.value = true
  translationError.value = null

  // 构建翻译配置
  const config = {
    ...localConfig,
    ai_provider: selectedProvider.value.provider_type,
    ai_model: effectiveModel.value || selectedProvider.value.default_model || 'gpt-4o',
    provider_id: selectedProviderId.value,
    batch_retry_limit: normalizeRetryLimit(localConfig.batch_retry_limit),
    custom_prompt: localConfig.custom_prompt?.trim() || null
  }

  // 如果有覆写参数，添加 provider_override
  const override = buildOverride()
  if (override) {
    config.provider_override = override
  }

  translationError.value = null
  await translateStore.saveConfig(config)
  if (translateStore.error) {
    translationError.value = translateStore.error
    return
  }

  const modpackVersionId = route.query.modpackVersionId
  const localPath = route.query.localPath
  if (!modpackVersionId || !localPath) return

  workflowStore.updateRouteContext({
    modpackVersionId,
    localPath,
    scanId: scanId.value || null
  })

  // 构建启动翻译请求，包含 provider_id、provider_override 以及范围过滤参数
  const startPayload = {
    modpack_version_id: modpackVersionId,
    local_path: localPath,
    config: {
      keep_original: config.keep_original,
      enable_cache: config.enable_cache,
      cache_scope: config.cache_scope,
      cache_reference_ids: config.cache_reference_ids || [],
      ai_provider: config.ai_provider,
      ai_model: config.ai_model,
      provider_id: config.provider_id,
      provider_override: config.provider_override || null,
      enable_glossary: config.enable_glossary,
      batch_size: config.batch_size,
      concurrency: config.concurrency,
      batch_retry_limit: config.batch_retry_limit,
      custom_prompt: config.custom_prompt || null,
      scan_id: scanId.value || null,
      selected_areas: localPackStore.selectedAreas.length > 0
          ? localPackStore.selectedAreas
          : null
    }
  }

  try {
    // 使用流式接口启动翻译，在流建立后尽快跳转到进度页
    let navigated = false
    await translateStore.startTranslation(
        modpackVersionId,
        localPath,
        startPayload.config,
        () => {
          // onStreamReady 回调：流已建立，立即跳转到进度页
          if (!navigated) {
            navigated = true
            const currentTaskId = translateStore.currentTaskId || workflowStore.currentTaskId || null
            workflowStore.updateRouteContext({
              taskId: currentTaskId,
              modpackVersionId,
              localPath,
              scanId: scanId.value || null
            })
            router.push(
              workflowStore.getStepLocation(3, {
                taskId: currentTaskId,
                modpackVersionId,
                localPath,
                scanId: scanId.value || null
              })
            )
          }
        }
    )
    // 如果流结束但尚未跳转（例如立即完成或出错），也尝试跳转
    if (!navigated) {
      if (translateStore.error) {
        // 出错时不跳转，留在配置页显示错误
        translationError.value = translateStore.error
        return
      }
      const currentTaskId = translateStore.currentTaskId || workflowStore.currentTaskId || null
      workflowStore.updateRouteContext({
        taskId: currentTaskId,
        modpackVersionId,
        localPath,
        scanId: scanId.value || null
      })
      router.push(
        workflowStore.getStepLocation(3, {
          taskId: currentTaskId,
          modpackVersionId,
          localPath,
          scanId: scanId.value || null
        })
      )
    }
  } catch (e) {
    translationError.value = translateStore.error || e.message || '翻译启动失败'
  } finally {
    translationStarting.value = false
  }
}

function handleGoBack() {
  translationError.value = null
  translateStore.error = null
  router.push(workflowStore.getBackLocation(2))
}

function handleRetry() {
  translationError.value = null
  handleStartTranslation()
}

function handleReset() {
  Object.assign(localConfig, {
    keep_original: true,
    enable_cache: true,
    cache_scope: 'version',
    cache_reference_ids: [],
    ai_provider: 'openai',
    ai_model: 'gpt-4o',
    enable_glossary: true,
    batch_size: 200,
    concurrency: 2,
    batch_retry_limit: getPersistedRetryLimit(),
    custom_prompt: ''
  })
  selectedProviderId.value = null
  overrideEnabled.value = false
  overrideConfig.api_base = ''
  overrideConfig.api_key = ''
  overrideConfig.default_model = ''
  selectedModelFromList.value = ''
  manualModelInput.value = ''
  modelList.value = []
  modelsError.value = null
  testResult.value = null
}

function resolveRestoredProviderId() {
  const preferred = localConfig.provider_id ?? translateStore.config.provider_id ?? null
  if (preferred === null || preferred === undefined || preferred === '') {
    return null
  }

  const parsed = Number.parseInt(String(preferred), 10)
  if (Number.isNaN(parsed)) return null
  return parsed
}

onMounted(async () => {
  await Promise.allSettled([
    settingsStore.loadAIProviders(),
    settingsStore.loadSettings()
  ])

  syncRetryLimitFromSettings()

  const restoredProviderId = resolveRestoredProviderId()
  const preferredProvider = enabledProviders.value.find(provider => provider.id === restoredProviderId)
  selectedProviderId.value = preferredProvider?.id || enabledProviders.value[0]?.id || null

  const restoredModel = String(localConfig.ai_model || translateStore.config.ai_model || '').trim()
  if (restoredModel) {
    modelInputMode.value = 'manual'
    manualModelInput.value = restoredModel
    localConfig.ai_model = restoredModel
  }

  if (scanId.value) {
    await ensureScanAreasLoaded()
    loadPreview()
  }
})
</script>

<template>
  <div class="translate-config-view">
    <div class="page-header-section">
      <h1 class="config-title">翻译配置</h1>
      <p class="config-subtitle">配置 AI 翻译参数，开始本地化工作流</p>
    </div>

    <ElAlert
        v-if="translateStore.error || translationError"
        type="error"
        :title="translationError || translateStore.error"
        closable
        class="config-error-alert"
        @close="translationError = null; translateStore.error = null"
    />

    <!-- 翻译启动错误恢复卡片 -->
    <div v-if="translationError" class="translation-error-card">
      <div class="error-card-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
      </div>
      <div class="error-card-content">
        <h3 class="error-card-title">翻译启动失败</h3>
        <p class="error-card-message">{{ translationError }}</p>
      </div>
      <div class="error-card-actions">
        <ElButton type="primary" @click="handleRetry">
          重试
        </ElButton>
        <ElButton @click="handleGoBack">
          返回上一步
        </ElButton>
      </div>
    </div>

    <div class="config-card">
      <div class="card-header">
        <svg class="card-header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="3"/>
          <path
              d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
        </svg>
        <span class="card-header-title">基本设置</span>
      </div>

      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">保留原文</span>
          <span class="setting-desc">输出的语言文件中是否保留英文原文作为注释</span>
        </div>
        <div class="setting-control">
          <ElSwitch v-model="localConfig.keep_original" active-color="var(--notion-primary)"/>
        </div>
      </div>

      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">启用缓存</span>
          <span class="setting-desc">复用已有翻译结果，节省 AI 调用成本</span>
        </div>
        <div class="setting-control">
          <ElSwitch v-model="localConfig.enable_cache" active-color="var(--notion-primary)"/>
        </div>
      </div>

      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">启用术语库</span>
          <span class="setting-desc">使用 CFPA 术语库 + 用户自定义术语约束翻译</span>
        </div>
        <div class="setting-control">
          <ElSwitch v-model="localConfig.enable_glossary" active-color="var(--notion-primary)"/>
        </div>
      </div>
    </div>

    <div v-if="scanId" class="config-card">
      <div class="card-header">
        <svg class="card-header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 6h18"/>
          <path d="M7 12h10"/>
          <path d="M10 18h4"/>
        </svg>
        <span class="card-header-title">扫描区域与交付偏好</span>
      </div>

      <div v-if="currentScanResult" class="scan-meta-grid">
        <div class="scan-meta-item">
          <span class="scan-meta-label">MC 版本</span>
          <span class="scan-meta-value">{{ currentScanResult.mc_version || '—' }}</span>
        </div>
        <div class="scan-meta-item">
          <span class="scan-meta-label">加载器</span>
          <span class="scan-meta-value">{{ currentScanResult.loader || '—' }}<template v-if="currentScanResult.loader_version"> {{ currentScanResult.loader_version }}</template></span>
        </div>
        <div class="scan-meta-item">
          <span class="scan-meta-label">游戏实例</span>
          <span class="scan-meta-value">{{ currentScanResult.game_name || currentScanResult.name || '—' }}</span>
        </div>
        <div class="scan-meta-item">
          <span class="scan-meta-label">工作根</span>
          <span class="scan-meta-value scan-meta-value--path">{{ currentScanResult.work_root || '—' }}</span>
        </div>
      </div>

      <div class="scan-summary-panel">
        <div class="scan-summary-grid">
          <div class="scan-summary-item">
            <span class="scan-summary-label">扫描区域</span>
            <span class="scan-summary-value">{{ scanAreaSelectionSummary.totalAreas }}</span>
          </div>
          <div class="scan-summary-item">
            <span class="scan-summary-label">已选区域</span>
            <span class="scan-summary-value">{{ scanAreaSelectionSummary.selectedAreas }}</span>
          </div>
          <div class="scan-summary-item">
            <span class="scan-summary-label">扫描文件</span>
            <span class="scan-summary-value">{{ scanAreaSelectionSummary.totalFiles }}</span>
          </div>
          <div class="scan-summary-item">
            <span class="scan-summary-label">本次选中文件</span>
            <span class="scan-summary-value">{{ scanAreaSelectionSummary.selectedFiles }}</span>
          </div>
        </div>
        <div v-if="scanAreaBadges.length > 0" class="scan-chip-list">
          <span v-for="area in scanAreaBadges" :key="area.type" class="scan-chip">
            {{ area.label }} · {{ area.count }}
          </span>
        </div>
      </div>

      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">包含 KubeJS 相关资源</span>
          <span class="setting-desc">批量控制 `kubejs_json`、`kubejs_lang`、`kubejs_js` 区域。关闭后这些区域不会进入本次翻译任务。</span>
        </div>
        <div class="setting-control">
          <ElSwitch v-model="includeKubejsAreas" :disabled="!hasKubejsAreas" active-color="var(--notion-primary)"/>
        </div>
      </div>

      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">优先按 FTBQuests 语言树路径处理</span>
          <span class="setting-desc">仅在同时扫描到 `ftb_quests` 与 `ftbquests_lang` 时可切换。开启后优先写入 `ftbquests/lang/zh_cn`，关闭后改回原始 quests SNBT 路径。</span>
        </div>
        <div class="setting-control">
          <ElSwitch v-model="preferFtbLangTree" :disabled="!hasFtbPriorityChoice" active-color="var(--notion-primary)"/>
        </div>
      </div>

      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">交付时附带 I18nUpdateMod</span>
          <span class="setting-desc">对应全局设置 `include_i18n_update_mod`，影响后续补丁目录生成时是否附带辅助模组文件。</span>
        </div>
        <div class="setting-control">
          <ElSwitch
            :model-value="includeI18nUpdateMod"
            :loading="deliverySettingsSaving"
            active-color="var(--notion-primary)"
            @change="handleToggleI18nUpdateMod"
          />
        </div>
      </div>

      <p class="delivery-note">
        当前页只控制前端选择与交付偏好；补丁目录生成阶段仍会基于后端返回的真实 `area_type`、`target_strategy` 与 `target_path` 落到 `config/`、`kubejs/`、`mods/`、`resourcepacks/` 等目录。
      </p>

      <div class="areas-embed">
        <TranslatableAreas />
      </div>
    </div>
 
    <div class="config-card">
      <div class="card-header">
        <svg class="card-header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round">
          <path
              d="M12 2a7 7 0 0 1 7 7c0 2.38-1.19 4.47-3 5.74V17a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 0 1 7-7z"/>
        </svg>
        <span class="card-header-title">AI 模型配置</span>
      </div>

      <!-- Provider 选择 -->
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">AI 提供商</span>
          <span class="setting-desc">选择已配置的 AI 提供商，或前往设置页添加</span>
        </div>
        <div class="setting-control setting-control--provider">
          <ElSelect
              v-model="selectedProviderId"
              class="notion-select"
              placeholder="选择提供商"
              clearable
          >
            <ElOption
                v-for="p in enabledProviders"
                :key="p.id"
                :value="p.id"
                :label="p.name"
            />
          </ElSelect>
          <ElButton
              v-if="openSettings"
              class="provider-settings-btn"
              text
              @click="openSettings('ai')"
          >
            前往设置
          </ElButton>
        </div>
      </div>

      <!-- Provider 信息展示 -->
      <div v-if="selectedProvider" class="provider-info-panel">
        <div class="provider-info-row">
          <span class="info-label">类型:</span>
          <span class="info-value">{{
              {
                openai: 'OpenAI',
                anthropic: 'Anthropic',
                deepseek: 'DeepSeek',
                qwen: '通义千问',
                zhipu: '智谱GLM',
                ollama: 'Ollama'
              }[selectedProvider.provider_type] || selectedProvider.provider_type
            }}</span>
        </div>
        <div class="provider-info-row">
          <span class="info-label">Base URL:</span>
          <span class="info-value">{{ selectedProvider.api_base || '默认' }}</span>
        </div>
        <div class="provider-info-row">
          <span class="info-label">API Key:</span>
          <span class="info-value">{{ selectedProvider.has_api_key ? '已配置' : '未配置' }}</span>
        </div>
        <div class="provider-info-row">
          <span class="info-label">默认模型:</span>
          <span class="info-value">{{ selectedProvider.default_model || '未设置' }}</span>
        </div>
        <div v-if="providerDescription" class="provider-desc">
          <span class="provider-desc-text">{{ providerDescription }}</span>
        </div>
      </div>

      <!-- 覆写开关 -->
      <div v-if="selectedProvider" class="setting-row">
        <div class="setting-info">
          <span class="setting-label">覆写提供商参数</span>
          <span class="setting-desc">临时替换此提供商的 Base URL、API Key 或模型，不修改已保存配置</span>
        </div>
        <div class="setting-control">
          <ElSwitch v-model="overrideEnabled" active-color="var(--notion-primary)"/>
        </div>
      </div>

      <!-- 覆写参数输入 -->
      <template v-if="overrideEnabled && selectedProvider">
        <div class="setting-row">
          <div class="setting-info">
            <span class="setting-label">覆写 Base URL</span>
            <span class="setting-desc">留空则使用提供商已保存的地址</span>
          </div>
          <div class="setting-control">
            <ElInput
                v-model="overrideConfig.api_base"
                class="notion-input"
                :placeholder="selectedProvider.api_base || '输入自定义 Base URL'"
            />
          </div>
        </div>

        <div class="setting-row">
          <div class="setting-info">
            <span class="setting-label">覆写 API Key</span>
            <span class="setting-desc">留空则使用提供商已保存的密钥</span>
          </div>
          <div class="setting-control">
            <ElInput
                v-model="overrideConfig.api_key"
                class="notion-input"
                type="password"
                show-password
                placeholder="输入临时 API Key"
            />
          </div>
        </div>
      </template>

      <!-- 模型选择 -->
      <div v-if="selectedProvider" class="setting-row">
        <div class="setting-info">
          <span class="setting-label">AI 模型</span>
          <span class="setting-desc">从模型列表选择或手工输入模型名称</span>
        </div>
        <div class="setting-control model-control">
          <div class="model-input-mode">
            <ElButton
                :type="modelInputMode === 'select' ? 'primary' : 'default'"
                size="small"
                @click="modelInputMode = 'select'"
            >
              从列表选择
            </ElButton>
            <ElButton
                :type="modelInputMode === 'manual' ? 'primary' : 'default'"
                size="small"
                @click="modelInputMode = 'manual'"
            >
              自定义
            </ElButton>
          </div>
          <ElSelect
              v-if="modelInputMode === 'select'"
              v-model="selectedModelFromList"
              class="notion-select model-select"
              placeholder="选择模型"
              :loading="loadingModels"
              clearable
              filterable
          >
            <ElOption
                v-for="m in modelList"
                :key="m.id"
                :value="m.id"
                :label="m.name || m.id"
            >
              <div class="model-option">
                <span class="model-option-id">{{ m.id }}</span>
                <span v-if="m.owned_by" class="model-option-owner">{{ m.owned_by }}</span>
              </div>
            </ElOption>
          </ElSelect>
          <ElInput
              v-else
              v-model="manualModelInput"
              class="notion-input"
              :placeholder="selectedProvider.default_model || 'gpt-4o'"
          />
          <div v-if="modelsError && modelInputMode === 'select'" class="model-error-hint">
            {{ modelsError }}，可切换到"手工输入"模式
          </div>
        </div>
      </div>

      <!-- 测试连接按钮 -->
      <div v-if="selectedProvider" class="setting-row test-row">
        <div class="setting-info">
          <span class="setting-label">测试连接</span>
          <span class="setting-desc">验证当前提供商 + 覆写参数 + 模型的最终可用性</span>
        </div>
        <div class="setting-control">
          <ElButton
              :loading="testingConnection"
              @click="handleTestConnection"
          >
            测试连接
          </ElButton>
        </div>
      </div>

      <div
          v-if="testResult"
          :class="['test-result', testResult.success ? 'test-result-success' : 'test-result-fail']"
      >
        <span v-if="testResult.success">
          连接成功 — 延迟 {{ testResult.latency_ms ?? '—' }}ms
          <span v-if="testResult.model_used">，使用模型: {{ testResult.model_used }}</span>
        </span>
        <span v-else>连接失败: {{ testResult.message || '未知错误' }}</span>
      </div>
    </div>

    <div class="config-card">
      <div class="card-header">
        <svg class="card-header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <polyline points="12 6 12 12 16 14"/>
        </svg>
        <span class="card-header-title">缓存参考范围</span>
      </div>

      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">缓存参考范围</span>
          <span class="setting-desc">指定翻译时参考哪些已有的缓存结果</span>
        </div>
        <div class="setting-control">
          <ElSelect v-model="localConfig.cache_scope" class="notion-select">
            <ElOption
                v-for="opt in cacheScopeOptions"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
            />
          </ElSelect>
        </div>
      </div>
    </div>

    <div class="config-card">
      <div class="card-header">
        <svg class="card-header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round">
          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
        </svg>
        <span class="card-header-title">翻译提示词补充</span>
      </div>

      <div class="setting-row setting-row--vertical">
        <div class="setting-info">
          <span class="setting-label">补充提示词</span>
          <span class="setting-desc">在系统默认提示词基础上追加的自定义要求，留空则仅使用默认提示词</span>
        </div>
        <div class="setting-control setting-control--full">
          <ElInput
              v-model="localConfig.custom_prompt"
              type="textarea"
              :rows="4"
              class="notion-textarea"
              placeholder="例如：翻译时保留所有颜色代码符号（如 §a），不要翻译玩家名称…"
          />
        </div>
      </div>
    </div>

    <div v-if="scanId" class="config-card">
      <div class="card-header">
        <svg class="card-header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
          <polyline points="10 9 9 9 8 9"/>
        </svg>
        <span class="card-header-title">待翻译文本预览</span>
      </div>

      <div v-if="previewLoading" class="preview-loading" v-loading="true" style="min-height: 80px;"/>
      <div v-else-if="previewError" class="preview-error">
        {{ previewError }}
      </div>
      <template v-else-if="previewItems.length > 0">
        <div class="preview-summary">
          共 <strong>{{ previewTotal }}</strong> 条待翻译文本
          <span v-if="previewTotal > PREVIEW_LIMIT" class="preview-expand-hint">
            （当前显示前 {{ PREVIEW_LIMIT }} 条）
          </span>
        </div>
        <div class="preview-table-wrap">
          <table class="preview-table">
            <thead>
            <tr>
              <th class="preview-col-file">文件</th>
              <th class="preview-col-key">键</th>
              <th class="preview-col-text">原文</th>
            </tr>
            </thead>
            <tbody>
            <tr v-for="(item, idx) in displayItems" :key="idx">
              <td class="preview-col-file" :title="item.source_file">{{ item.source_file || '—' }}</td>
              <td class="preview-col-key" :title="item.key">{{ item.key || '—' }}</td>
              <td class="preview-col-text" :title="item.original_text">{{ item.original_text || '—' }}</td>
            </tr>
            </tbody>
          </table>
        </div>
        <div v-if="previewTotal > PREVIEW_LIMIT" class="preview-expand-action">
          <ElButton
              text
              size="small"
              @click="previewExpanded = !previewExpanded"
          >
            {{ previewExpanded ? '收起' : `展开全部 ${previewTotal} 条` }}
          </ElButton>
        </div>
      </template>
      <div v-else class="preview-empty">
        暂无待翻译文本数据
      </div>
    </div>

    <ElCollapse v-model="activeCollapse" class="config-collapse">
      <ElCollapseItem title="高级设置" name="advanced">
        <div class="advanced-body">
          <div class="setting-row">
            <div class="setting-info">
              <span class="setting-label">每批翻译条数</span>
              <span class="setting-desc">每批次发送给 AI 的翻译条目数量</span>
            </div>
            <div class="setting-control">
              <ElInputNumber
                  v-model="localConfig.batch_size"
                  :min="1"
                  :max="1000"
                  class="notion-input-number"
              />
            </div>
          </div>

          <div class="setting-row">
            <div class="setting-info">
              <span class="setting-label">并发请求数</span>
              <span class="setting-desc">同时发起的 AI 请求数量</span>
            </div>
            <div class="setting-control">
              <ElInputNumber
                  v-model="localConfig.concurrency"
                  :min="1"
                  :max="10"
                  class="notion-input-number"
              />
            </div>
          </div>

          <div class="setting-row">
            <div class="setting-info">
              <span class="setting-label">单批失败自动重试</span>
              <span class="setting-desc">仅重试当前翻译批次，范围 0~3；0 表示关闭自动重试。默认值读取系统设置，可在本次任务中临时覆盖。</span>
            </div>
            <div class="setting-control">
              <ElInputNumber
                  v-model="localConfig.batch_retry_limit"
                  :min="0"
                  :max="3"
                  :step="1"
                  class="notion-input-number"
              />
            </div>
          </div>

          <div class="warning-text">
            较高的并发数可能导致 API 限流，建议保持 3 以内；自动重试仅对当前失败批次生效，不会整项任务从头重跑。
          </div>
        </div>
      </ElCollapseItem>
    </ElCollapse>

    <div class="action-bar">
      <ElButton
          type="primary"
          size="large"
          class="btn-start"
          :disabled="!canStart"
          :loading="translationStarting"
          @click="handleStartTranslation"
      >
        {{ translationStarting ? '正在启动...' : '开始翻译' }}
      </ElButton>
      <ElButton
          size="large"
          class="btn-reset"
          :disabled="translationStarting"
          @click="handleReset"
      >
        重置配置
      </ElButton>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.translate-config-view {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px 24px 60px;
}

/* ── Page Header ──────────────────────────────────── */
.page-header-section {
  margin-bottom: 28px;
}

.config-title {
  font-family: var(--notion-font-sans);
  font-size: var(--notion-font-size-h3);
  font-weight: 600;
  color: var(--notion-ink-deep);
  margin: 0 0 6px 0;
  line-height: var(--notion-line-height-h3);
}

.config-subtitle {
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-slate);
  margin: 0;
  line-height: var(--notion-line-height-body-sm);
}

/* ── Error Alert ──────────────────────────────────── */
.config-error-alert {
  margin-bottom: 16px;
}

/* ── Translation Error Card ───────────────────────── */
.translation-error-card {
  background: var(--fluent-surface-danger-subtle, #fdf2f2);
  border: 1px solid var(--notion-semantic-error, #e53e3e);
  border-radius: var(--notion-rounded-lg);
  padding: 24px;
  margin-bottom: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 16px;
}

.error-card-icon {
  width: 48px;
  height: 48px;
  color: var(--notion-semantic-error);
}

.error-card-icon svg {
  width: 100%;
  height: 100%;
}

.error-card-content {
  flex: 1;
}

.error-card-title {
  font-size: var(--notion-font-size-body, 14px);
  font-weight: 600;
  color: var(--notion-ink-deep);
  margin: 0 0 8px 0;
}

.error-card-message {
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-ink);
  margin: 0;
  line-height: var(--notion-line-height-body);
  word-break: break-word;
}

.error-card-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

/* ── Config Cards ─────────────────────────────────── */
.config-card {
  background: var(--notion-canvas);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
  padding: var(--notion-spacing-xl);
  margin-bottom: var(--notion-spacing-md);
}

.card-header {
  display: flex;
  align-items: center;
  gap: var(--notion-spacing-xs);
  margin-bottom: var(--notion-spacing-md);
  padding-bottom: var(--notion-spacing-sm);
  border-bottom: 1px solid var(--notion-hairline);
}

.card-header-icon {
  width: 18px;
  height: 18px;
  color: var(--notion-primary);
  flex-shrink: 0;
}

.card-header-title {
  font-size: var(--notion-font-size-body);
  font-weight: 600;
  color: var(--notion-ink);
}

/* ── Setting Rows ─────────────────────────────────── */
.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;

  & + & {
    border-top: 1px solid var(--notion-hairline-soft);
  }
}

.setting-info {
  flex: 1;
  min-width: 0;
  padding-right: var(--notion-spacing-xl);
}

.setting-label {
  display: block;
  font-size: var(--notion-font-size-body-sm);
  font-weight: 600;
  color: var(--notion-ink);
  margin-bottom: 2px;
}

.setting-desc {
  display: block;
  font-size: var(--notion-font-size-micro);
  color: var(--notion-steel);
  line-height: var(--notion-line-height-caption);
}

.setting-control {
  flex-shrink: 0;
}

.setting-control--provider {
  display: flex;
  align-items: center;
  gap: 10px;
}

.provider-settings-btn {
  flex-shrink: 0;
}

/* ── Provider Info Panel ──────────────────────────── */
.provider-info-panel {
  background: var(--fluent-surface-2);
  border: 1px solid var(--notion-hairline-soft);
  border-radius: var(--notion-rounded-md);
  padding: var(--notion-spacing-md);
  margin-bottom: var(--notion-spacing-sm);
}

.provider-info-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 4px 0;
  font-size: var(--notion-font-size-caption);
}

.info-label {
  color: var(--notion-steel);
  min-width: 80px;
  flex-shrink: 0;
}

.info-value {
  color: var(--notion-ink);
  word-break: break-all;
}

/* ── Model Control ────────────────────────────────── */
.model-control {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}

.model-input-mode {
  display: flex;
  gap: 4px;
}

.model-select {
  width: 260px;
}

.model-option {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.model-option-id {
  font-weight: 500;
}

.model-option-owner {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-steel);
  margin-left: 8px;
}

.model-error-hint {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-semantic-warning);
  text-align: right;
  max-width: 260px;
}

/* ── Test Result ──────────────────────────────────── */
.test-row {
  margin-top: 4px;
}

.test-result {
  margin-top: 8px;
  padding: 10px 14px;
  border-radius: var(--notion-rounded-sm);
  font-size: var(--notion-font-size-caption);
}

.test-result-success {
  color: var(--notion-semantic-success);
  background-color: var(--fluent-surface-success-subtle);
  border: 1px solid var(--notion-semantic-success);
}

.test-result-fail {
  color: var(--notion-semantic-error);
  background-color: var(--fluent-surface-danger-subtle);
  border: 1px solid var(--notion-semantic-error);
}

/* ── Custom Prompt Textarea ───────────────────────── */
.setting-row--vertical {
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.setting-control--full {
  width: 100%;
  flex-shrink: 1;
}

.notion-textarea {
  width: 100%;

  :deep(.el-textarea__inner) {
    border: 1px solid var(--notion-hairline-strong);
    border-radius: var(--notion-rounded-md);
    box-shadow: none;
    background: var(--notion-canvas);
    padding: var(--notion-spacing-sm) var(--notion-spacing-md);
    font-size: var(--notion-font-size-body);
    color: var(--notion-ink);
    line-height: var(--notion-line-height-body);
    resize: vertical;
    min-height: 80px;

    &::placeholder {
      color: var(--notion-muted);
    }

    &:hover {
      border-color: var(--notion-steel);
    }

    &:focus {
      border: 2px solid var(--notion-primary);
    }
  }
}

.scan-meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--notion-spacing-sm);
  margin-bottom: var(--notion-spacing-md);
}

.scan-meta-item,
.scan-summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  background: var(--fluent-surface-2);
  border: 1px solid var(--notion-hairline-soft);
  border-radius: var(--notion-rounded-md);
}

.scan-meta-label,
.scan-summary-label {
  font-size: var(--notion-font-size-micro-uppercase);
  color: var(--notion-steel);
  font-weight: 600;
  letter-spacing: 0.06em;
}

.scan-meta-value,
.scan-summary-value {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 600;
  color: var(--notion-ink);
}

.scan-meta-value--path {
  word-break: break-all;
}

.scan-summary-panel {
  margin-bottom: var(--notion-spacing-sm);
}

.scan-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--notion-spacing-sm);
  margin-bottom: var(--notion-spacing-sm);
}

.scan-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.scan-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--notion-surface);
  border: 1px solid var(--notion-hairline);
  color: var(--notion-charcoal);
  font-size: var(--notion-font-size-micro);
}

.delivery-note {
  margin: var(--notion-spacing-sm) 0 0;
  padding: 10px 14px;
  font-size: var(--notion-font-size-micro);
  color: var(--notion-steel);
  background: var(--fluent-surface-2);
  border: 1px solid var(--notion-hairline-soft);
  border-radius: var(--notion-rounded-sm);
  line-height: var(--notion-line-height-caption);
}

.areas-embed {
  margin-top: var(--notion-spacing-md);
}

/* ── Preview Section ──────────────────────────────── */
.preview-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 80px;
}

.preview-error {
  padding: 12px 16px;
  color: var(--notion-semantic-error);
  background: var(--fluent-surface-danger-subtle);
  border: 1px solid var(--notion-semantic-error);
  border-radius: var(--notion-rounded-sm);
  font-size: var(--notion-font-size-caption);
}

.preview-summary {
  font-size: var(--notion-font-size-caption);
  color: var(--notion-ink);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--notion-hairline-soft);
}

.preview-expand-hint {
  color: var(--notion-steel);
  margin-left: 4px;
}

.preview-table-wrap {
  max-height: 320px;
  overflow-y: auto;
  border: 1px solid var(--notion-hairline-soft);
  border-radius: var(--notion-rounded-sm);
}

.preview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--notion-font-size-micro);
  table-layout: fixed;
}

.preview-table th {
  background: var(--fluent-surface-2);
  color: var(--notion-steel);
  font-weight: 600;
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--notion-hairline);
  position: sticky;
  top: 0;
  z-index: 1;
}

.preview-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--notion-hairline-soft);
  color: var(--notion-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.preview-table tr:hover td {
  background: var(--fluent-surface-2);
}

.preview-col-file {
  width: 35%;
}

.preview-col-key {
  width: 25%;
}

.preview-col-text {
  width: 40%;
}

.preview-expand-action {
  margin-top: 8px;
  text-align: center;
}

.preview-empty {
  padding: 24px 0;
  text-align: center;
  color: var(--notion-muted);
  font-size: var(--notion-font-size-caption);
}

/* ── Notion-styled Input ──────────────────────────── */
.notion-input {
  width: 220px;

  :deep(.el-input__wrapper) {
    height: 44px;
    border: 1px solid var(--notion-hairline-strong);
    border-radius: var(--notion-rounded-md);
    box-shadow: none;
    background: var(--notion-canvas);
    padding: var(--notion-spacing-sm) var(--notion-spacing-md);
    transition: border-color var(--notion-transition-fast);

    .el-input__inner {
      font-size: var(--notion-font-size-body);
      color: var(--notion-ink);
      line-height: var(--notion-line-height-body);

      &::placeholder {
        color: var(--notion-muted);
      }
    }

    &:hover {
      border-color: var(--notion-steel);
    }

    &.is-focus {
      border: 2px solid var(--notion-primary);
    }
  }
}

/* ── Notion-styled Select ─────────────────────────── */
.notion-select {
  width: 220px;

  :deep(.el-select__wrapper) {
    height: 44px;
    border: 1px solid var(--notion-hairline-strong);
    border-radius: var(--notion-rounded-md);
    box-shadow: none;
    background: var(--notion-canvas);
    padding: var(--notion-spacing-sm) var(--notion-spacing-md);
    transition: border-color var(--notion-transition-fast);
    cursor: pointer;

    .el-select__placeholder {
      color: var(--notion-muted);
    }

    .el-select__selected-item {
      font-size: var(--notion-font-size-body);
      color: var(--notion-ink);
    }

    &:hover {
      border-color: var(--notion-steel);
    }

    &.is-focused {
      border: 2px solid var(--notion-primary);
    }
  }
}

/* ── Notion-styled InputNumber ────────────────────── */
.notion-input-number {
  width: 140px;

  :deep(.el-input-number__decrease),
  :deep(.el-input-number__increase) {
    border: 1px solid var(--notion-hairline-strong);
    background: var(--notion-canvas);
    color: var(--notion-slate);
    border-radius: 0;

    &:hover {
      color: var(--notion-primary);
    }
  }

  :deep(.el-input__wrapper) {
    height: 44px;
    border: 1px solid var(--notion-hairline-strong);
    border-radius: 0;
    box-shadow: none;
    background: var(--notion-canvas);

    .el-input__inner {
      font-size: var(--notion-font-size-body);
      color: var(--notion-ink);
    }

    &:hover {
      border-color: var(--notion-steel);
    }
  }
}

/* ── Provider Description ─────────────────────────── */
.provider-desc {
  margin-top: 8px;
  padding: 10px 14px;
  background: var(--notion-tint-lavender);
  border: 1px solid var(--notion-brand-purple-300);
  border-radius: var(--notion-rounded-sm);
}

.provider-desc-text {
  font-size: var(--notion-font-size-caption);
  color: var(--notion-brand-purple-800);
  line-height: var(--notion-line-height-caption);
}

/* ── Collapse (Advanced Settings) ─────────────────── */
.config-collapse {
  margin-bottom: var(--notion-spacing-md);
  border-radius: var(--notion-rounded-lg);
  overflow: hidden;

  :deep(.el-collapse-item__header) {
    height: auto;
    padding: var(--notion-spacing-lg) var(--notion-spacing-xl);
    font-size: var(--notion-font-size-body);
    font-weight: 600;
    color: var(--notion-ink);
    background: var(--notion-canvas);
    border: 1px solid var(--notion-hairline);
    border-radius: var(--notion-rounded-lg);
    transition: border-radius var(--notion-transition-fast);

    &:hover {
      color: var(--notion-primary);
    }
  }

  :deep(.el-collapse-item__wrap) {
    background: var(--notion-canvas);
    border: 1px solid var(--notion-hairline);
    border-top: none;
    border-radius: 0 0 var(--notion-rounded-lg) var(--notion-rounded-lg);
  }

  :deep(.el-collapse-item__content) {
    padding: var(--notion-spacing-xl);
  }
}

.advanced-body {
  .setting-row:first-child {
    padding-top: 0;
  }
}

.warning-text {
  margin-top: 12px;
  padding: 10px 14px;
  font-size: var(--notion-font-size-micro);
  color: var(--notion-semantic-warning);
  background: var(--notion-tint-peach);
  border: 1px solid var(--notion-brand-orange-deep);
  border-radius: var(--notion-rounded-sm);
  line-height: var(--notion-line-height-caption);
}

/* ── Action Bar ───────────────────────────────────── */
.action-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: var(--notion-spacing-xxl);
}

.btn-start {
  --el-button-bg-color: var(--notion-primary);
  --el-button-border-color: var(--notion-primary);
  --el-button-hover-bg-color: var(--notion-primary-pressed);
  --el-button-hover-border-color: var(--notion-primary-pressed);
  --el-button-active-bg-color: var(--notion-primary-deep);
  --el-button-active-border-color: var(--notion-primary-deep);
  --el-button-disabled-bg-color: var(--notion-hairline);
  --el-button-disabled-border-color: var(--notion-hairline);
  --el-button-disabled-text-color: var(--notion-muted);
  border-radius: var(--notion-rounded-md);
  padding: 10px 18px;
  font-size: var(--notion-font-size-body-sm);
  font-weight: 500;
}

.btn-reset {
  --el-button-bg-color: transparent;
  --el-button-border-color: transparent;
  --el-button-text-color: var(--notion-ink);
  --el-button-hover-bg-color: var(--notion-surface);
  --el-button-hover-border-color: transparent;
  --el-button-active-bg-color: var(--notion-surface);
  border-radius: var(--notion-rounded-sm);
  padding: 8px 12px;
  font-size: var(--notion-font-size-body-sm);
  font-weight: 500;
}

@media (max-width: 576px) {
  .translate-config-view {
    padding: 16px 16px 40px;
  }

  .setting-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .setting-info {
    padding-right: 0;
  }

  .setting-control {
    width: 100%;
  }

  .notion-input,
  .notion-select {
    width: 100%;
  }

  .model-control {
    align-items: flex-start;
    width: 100%;
  }

  .model-select {
    width: 100%;
  }

  .action-bar {
    flex-direction: column;

    .el-button {
      width: 100%;
    }
  }
}
</style>
