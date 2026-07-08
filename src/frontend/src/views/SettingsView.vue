<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import {
  ElButton,
  ElInput,
  ElSelect,
  ElOption,
  ElSwitch,
  ElForm,
  ElFormItem,
  ElAlert,
  ElEmpty,
  ElTabs,
  ElTabPane,
  ElPopconfirm,
  ElDialog,
  ElInputNumber,
  ElDivider,
  ElMessage,
  vLoading
} from 'element-plus'
import { useSettingsStore } from '@/stores/settings'
import { isDark, toggleDark } from '@/composables/useTheme.js'
import { asBooleanSetting } from '@/utils/localizationDelivery'

const props = defineProps({
  dialogMode: {
    type: Boolean,
    default: false
  },
  initialTab: {
    type: String,
    default: 'ai'
  }
})

const emit = defineEmits(['update:dialogVisible'])

const store = useSettingsStore()

const activeTab = ref(props.initialTab || 'general')

watch(() => props.initialTab, (val) => {
  if (val) activeTab.value = val
})

const providerTypeMeta = {
  openai: { label: 'OpenAI', color: 'green' },
  anthropic: { label: 'Anthropic', color: 'orange' },
  deepseek: { label: 'DeepSeek', color: 'blue' },
  qwen: { label: '通义千问', color: 'purple' },
  zhipu: { label: '智谱GLM', color: 'red' },
  ollama: { label: 'Ollama', color: 'grey' }
}

const providerBaseUrls = {
  openai: 'https://api.openai.com/v1',
  anthropic: 'https://api.anthropic.com',
  deepseek: 'https://api.deepseek.com',
  qwen: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  zhipu: 'https://open.bigmodel.cn/api/paas/v4',
  ollama: 'http://localhost:11434'
}

const providerTypeTagType = {
  openai: '',
  anthropic: 'warning',
  deepseek: '',
  qwen: '',
  zhipu: 'danger',
  ollama: 'info'
}

const modalVisible = ref(false)
const modalTitle = ref('添加提供商')
const editingProviderId = ref(null)
const savingProvider = ref(false)

const defaultForm = () => ({
  name: '',
  provider_type: 'openai',
  api_key: '',
  api_base: '',
  default_model: '',
  is_enabled: true
})

const form = reactive(defaultForm())

const modelList = ref([])
const loadingModels = ref(false)
const modelsError = ref(null)
const modelsDirty = ref(false)

const modelOptions = computed(() => {
  const options = Array.isArray(modelList.value) ? [...modelList.value] : []
  const currentModel = form.default_model.trim()

  if (currentModel && !options.some(model => model.id === currentModel)) {
    options.unshift({
      id: currentModel,
      name: currentModel,
      owned_by: '当前输入',
      isManual: true
    })
  }

  return options
})

const modelFetchHint = computed(() => {
  if (loadingModels.value) {
    return '正在从后端获取模型列表...'
  }
  if (modelsDirty.value) {
    return '连接参数已变更，请重新获取模型列表'
  }
  if (modelList.value.length > 0) {
    return `已加载 ${modelList.value.length} 个模型，可直接选择或手动输入`
  }
  return '可先获取模型列表，也可直接手动输入模型名称'
})

const apiKeyModified = ref(false)
const apiKeyPlaceholder = '不修改则保持原值'

const testingProviderId = ref(null)
const testResult = ref(null)
const testResultProviderId = ref(null)
const testingModalProvider = ref(false)
const modalTestResult = ref(null)

const generalForm = reactive({
  language: 'zh-CN',
  isDark: isDark.value,
  checkUpdateOnStart: true,
  translateBatchRetryLimit: 3,
  targetMinecraftRoot: '',
  patchOutputDir: '',
  includeI18nUpdateMod: false,
  i18nModCacheDir: ''
})

const cacheForm = reactive({
  autoClean: true,
  maxEntries: 10000,
  hitStrategy: 'standard'
})

const cacheStats = computed(() => store.cacheStats)
const cacheStatsScopeEntries = computed(() => {
  const source = cacheStats.value?.by_scope || {}
  return [
    { key: 'version', label: '仅当前版本', value: Number(source.version || 0) },
    { key: 'modpack', label: '同一整合包', value: Number(source.modpack || 0) },
    { key: 'all', label: '全局复用', value: Number(source.all || 0) }
  ]
})
const cacheStatsScopeMax = computed(() => {
  return cacheStatsScopeEntries.value.reduce((max, item) => Math.max(max, item.value), 0)
})
const cacheStatsLanguageEntries = computed(() => {
  const source = cacheStats.value?.by_target_language || {}
  return Object.entries(source)
    .map(([language, value]) => ({ language, value: Number(value || 0) }))
    .sort((a, b) => b.value - a.value)
})
const cacheStatsLanguageMax = computed(() => {
  return cacheStatsLanguageEntries.value.reduce((max, item) => Math.max(max, item.value), 0)
})

function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN')
}

function openAddModal() {
  modalTitle.value = '添加提供商'
  editingProviderId.value = null
  Object.assign(form, defaultForm())
  apiKeyModified.value = false
  resetModelFetchState()
  modalTestResult.value = null
  modalVisible.value = true
}

function openEditModal(provider) {
  modalTitle.value = '编辑提供商'
  editingProviderId.value = provider.id
  Object.assign(form, {
    name: provider.name || '',
    provider_type: provider.provider_type || 'openai',
    api_key: '',
    api_base: provider.api_base || '',
    default_model: provider.default_model || '',
    is_enabled: provider.is_enabled !== false
  })
  apiKeyModified.value = false
  resetModelFetchState()
  modalTestResult.value = null
  modalVisible.value = true
}

function resetModelFetchState() {
  modelList.value = []
  loadingModels.value = false
  modelsError.value = null
  modelsDirty.value = false
}

function markModelListDirty() {
  modalTestResult.value = null
  modelsError.value = null

  if (modelList.value.length > 0) {
    modelsDirty.value = true
  }
}

function resolveRequestErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail

  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }

  if (Array.isArray(detail)) {
    const joined = detail
      .map(item => item?.msg || item?.message)
      .filter(Boolean)
      .join('；')

    if (joined) {
      return joined
    }
  }

  return error?.message || fallback
}

function onProviderTypeChange(value) {
  form.api_base = providerBaseUrls[value] || ''
  markModelListDirty()
}

function onApiBaseInput() {
  markModelListDirty()
}

function onApiKeyInput() {
  apiKeyModified.value = true
  markModelListDirty()
}

async function handleSubmit() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入提供商名称')
    return
  }

  savingProvider.value = true
  try {
    if (editingProviderId.value !== null) {
      const payload = {
        name: form.name.trim(),
        provider_type: form.provider_type,
        api_base: form.api_base.trim() || null,
        default_model: form.default_model.trim() || null,
        is_enabled: form.is_enabled
      }

      if (apiKeyModified.value) {
        payload.api_key = form.api_key
      }

      await store.editAIProvider(editingProviderId.value, payload)
      ElMessage.success('提供商已更新')
    } else {
      const payload = {
        name: form.name.trim(),
        provider_type: form.provider_type,
        api_key: form.api_key || null,
        api_base: form.api_base.trim() || null,
        default_model: form.default_model.trim() || null,
        is_enabled: form.is_enabled
      }
      await store.addAIProvider(payload)
      ElMessage.success('提供商已添加')
    }

    modalVisible.value = false
  } catch (e) {
    // store 已经设置了 error，这里不再重复提示
  } finally {
    savingProvider.value = false
  }
}

async function handleDelete(providerId) {
  try {
    await store.removeAIProvider(providerId)
    ElMessage.success('提供商已删除')
  } catch (e) {
    // store 已经设置了 error
  }
}

async function handleTestConnection(providerId) {
  testingProviderId.value = providerId
  testResult.value = null
  testResultProviderId.value = null
  const result = await store.testConnection(providerId)
  testResult.value = result
  testResultProviderId.value = providerId
  testingProviderId.value = null
}

function buildProviderOverrideFromForm() {
  const override = {
    provider_type: form.provider_type
  }

  if (form.api_base.trim()) {
    override.api_base = form.api_base.trim()
  }

  if (apiKeyModified.value) {
    override.api_key = form.api_key
  }

  if (form.default_model.trim()) {
    override.default_model = form.default_model.trim()
  }

  return override
}

async function handleLoadModels() {
  loadingModels.value = true
  modelsError.value = null

  try {
    const override = buildProviderOverrideFromForm()
    const providerId = editingProviderId.value ?? null
    const data = await store.loadAIModels(providerId, override)

    modelList.value = Array.isArray(data?.models) ? data.models : []
    modelsDirty.value = false

    if (modelList.value.length > 0) {
      ElMessage.success(`已获取 ${modelList.value.length} 个模型`)
    } else {
      ElMessage.warning('未获取到可用模型，仍可手动输入模型名称')
    }
  } catch (e) {
    modelList.value = []
    modelsDirty.value = false
    modelsError.value = resolveRequestErrorMessage(e, '获取模型列表失败')
    ElMessage.warning(modelsError.value)
  } finally {
    loadingModels.value = false
  }
}

async function handleModalTestConnection() {
  testingModalProvider.value = true
  modalTestResult.value = null

  try {
    const override = buildProviderOverrideFromForm()
    const model = form.default_model.trim() || null
    const providerId = editingProviderId.value ?? null
    const result = await store.testConnection(providerId, override, model)
    modalTestResult.value = result

    if (result.success) {
      ElMessage.success(`连接成功！延迟 ${result.latency_ms ?? '—'}ms${result.model_used ? '，模型: ' + result.model_used : ''}`)
    } else {
      ElMessage.error(`连接失败: ${result.message || '未知错误'}`)
    }
  } finally {
    testingModalProvider.value = false
  }
}

function normalizeRetryLimit(value, fallback = 3) {
  const parsed = Number.parseInt(String(value ?? fallback), 10)
  if (Number.isNaN(parsed)) return fallback
  return Math.min(3, Math.max(0, parsed))
}

async function handleSaveGeneralSettings() {
  try {
    await store.saveSettings({
      translate_batch_retry_limit: String(normalizeRetryLimit(generalForm.translateBatchRetryLimit)),
      target_minecraft_root: generalForm.targetMinecraftRoot,
      patch_output_dir: generalForm.patchOutputDir,
      include_i18n_update_mod: generalForm.includeI18nUpdateMod ? 'true' : 'false',
      i18n_mod_cache_dir: generalForm.i18nModCacheDir
    })
    ElMessage.success('通用设置已保存')
  } catch (_) {
    // store 已写入错误信息
  }
}

async function clearAllCache() {
  try {
    const result = await store.clearAllCache()
    const clearedEntries = Number(result?.cleared_entries || 0)
    ElMessage.success(clearedEntries > 0 ? `已清空 ${clearedEntries} 条缓存` : '所有缓存已清空')
    await store.loadCacheStats()
  } catch (_) {
    // store 已写入错误信息
  }
}

watch(() => store.settings, (settings) => {
  generalForm.translateBatchRetryLimit = normalizeRetryLimit(settings?.translate_batch_retry_limit, 3)
  generalForm.targetMinecraftRoot = settings?.target_minecraft_root || ''
  generalForm.patchOutputDir = settings?.patch_output_dir || ''
  generalForm.includeI18nUpdateMod = asBooleanSetting(settings?.include_i18n_update_mod, false)
  generalForm.i18nModCacheDir = settings?.i18n_mod_cache_dir || ''
}, { immediate: true, deep: true })

onMounted(() => {
  store.loadSettings()
  store.loadAIProviders()
  store.loadCacheStats()
})
</script>

<template>
  <component
    :is="dialogMode ? ElDialog : 'div'"
    :class="dialogMode ? 'settings-dialog' : null"
    v-bind="dialogMode ? {
      modelValue: true,
      title: '系统设置',
      width: '820px',
      closeOnClickModal: false,
      alignCenter: true
    } : {}"
    @update:model-value="dialogMode && emit('update:dialogVisible', false)"
  >
    <div v-loading="store.loading" class="settings-view" :class="{ 'settings-view--dialog': dialogMode }">
      <section v-if="!dialogMode" class="settings-hero">
        <div class="settings-hero-copy">
          <div class="settings-hero-meta">
            <span class="settings-hero-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </span>
            <span class="settings-kicker">系统设置</span>
          </div>
          <h1 class="page-title">统一管理运行环境、提供商与缓存策略</h1>
          <p class="settings-subtitle">保持桌面工作区配置集中、状态清晰，并减少干扰性视觉元素。</p>
        </div>
        <div class="settings-summary-card">
          <span class="summary-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 2 4 6v6c0 5 3.5 9.5 8 10 4.5-.5 8-5 8-10V6l-8-4z" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          </span>
          <div class="summary-body">
            <span class="summary-label">已配置提供商</span>
            <span class="summary-value">{{ store.aiProviders.length }}</span>
            <span class="summary-hint">可在此维护默认模型与连接状态</span>
          </div>
        </div>
      </section>

      <ElAlert
        v-if="store.error"
        type="error"
        :title="store.error"
        closable
        @close="store.error = null"
        class="error-alert"
      />

      <ElTabs v-model="activeTab">
        <ElTabPane label="通用设置" name="general">
          <div class="tab-header tab-header--stacked">
            <div>
              <h2 class="tab-section-title">
                <span class="tab-section-title-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="3" />
                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
                  </svg>
                </span>
                通用设置
              </h2>
              <p class="section-caption">语言、主题与启动行为。</p>
            </div>
          </div>

          <div class="settings-card">
            <ElForm label-width="180px" class="settings-form" label-position="left">
              <ElFormItem label="语言">
                <ElSelect v-model="generalForm.language" style="width: 220px">
                  <ElOption value="zh-CN" label="简体中文" />
                  <ElOption value="en" label="English" />
                </ElSelect>
              </ElFormItem>
              <ElFormItem label="主题">
                <ElSelect v-model="generalForm.isDark" style="width: 220px" @change="toggleDark()">
                  <ElOption :value="true" label="深色主题" />
                  <ElOption :value="false" label="浅色主题" />
                </ElSelect>
              </ElFormItem>
              <ElFormItem label="启动时检查更新">
                <ElSwitch v-model="generalForm.checkUpdateOnStart" />
              </ElFormItem>
              <ElFormItem label="翻译批次重试次数">
                <div class="general-inline-field">
                  <ElInputNumber
                    v-model="generalForm.translateBatchRetryLimit"
                    :min="0"
                    :max="3"
                    :step="1"
                  />
                  <span class="form-hint">当 AI 输出解析失败时自动重试的次数，0 表示不自动重试，最大值为 3。</span>
                </div>
              </ElFormItem>
              <ElFormItem label="目标 Minecraft 根目录">
                <div class="general-field-stack">
                  <ElInput
                    v-model="generalForm.targetMinecraftRoot"
                    placeholder="例如：D:/Game/.minecraft"
                    class="general-wide-input"
                  />
                  <span class="form-hint">用于本地整合包扫描与补丁交付时推断实例根目录，建议填写实际游戏根目录。</span>
                </div>
              </ElFormItem>
              <ElFormItem label="补丁输出目录">
                <div class="general-field-stack">
                  <ElInput
                    v-model="generalForm.patchOutputDir"
                    placeholder="例如：D:/Game/MC/Patches"
                    class="general-wide-input"
                  />
                  <span class="form-hint">留空时由后端使用默认工作区目录；填写后，生成的整合包补丁目录会优先输出到此路径。</span>
                </div>
              </ElFormItem>
              <ElFormItem label="附带 I18nUpdateMod">
                <div class="general-inline-field">
                  <ElSwitch v-model="generalForm.includeI18nUpdateMod" />
                  <span class="form-hint">启用后，补丁目录生成阶段会尝试复用或下载 `I18nUpdateMod` 并放入 `mods/` 目录；失败提示将在交付页展示。</span>
                </div>
              </ElFormItem>
              <ElFormItem label="I18nUpdateMod 缓存目录">
                <div class="general-field-stack">
                  <ElInput
                    v-model="generalForm.i18nModCacheDir"
                    placeholder="例如：D:/Game/MC/.mcpacklocalizer-cache/i18n-mod"
                    class="general-wide-input"
                  />
                  <span class="form-hint">用于缓存下载过的 `I18nUpdateMod` 文件，便于后续补丁生成时复用。</span>
                </div>
              </ElFormItem>
            </ElForm>
            <div class="settings-actions-row">
              <ElButton type="primary" @click="handleSaveGeneralSettings">保存通用设置</ElButton>
            </div>
          </div>
        </ElTabPane>

        <ElTabPane label="AI 提供商" name="ai">
          <div class="tab-header">
            <div>
              <h2 class="tab-section-title">
                <span class="tab-section-title-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 2a4 4 0 0 0-4 4v2H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10a2 2 0 0 0-2-2h-2V6a4 4 0 0 0-4-4z" />
                    <circle cx="9" cy="14" r="1" />
                    <circle cx="15" cy="14" r="1" />
                    <path d="M9 18h6" />
                  </svg>
                </span>
                AI 提供商配置
              </h2>
              <p class="section-caption">所有提供商配置均保存在本地，不会上传或同步到任何远端服务</p>
            </div>
            <ElButton type="primary" @click="openAddModal">添加提供商</ElButton>
          </div>

          <ElEmpty
            v-if="store.aiProviders.length === 0"
            description="暂无配置的 AI 提供商，点击上方按钮添加"
            class="provider-empty"
          />

          <div v-else class="provider-list">
            <div
              v-for="provider in store.aiProviders"
              :key="provider.id"
              class="provider-card"
            >
              <div class="provider-card-main">
an                <div
                  class="provider-avatar"
                  :data-type="provider.provider_type"
                  aria-hidden="true"
                >
                  {{ (providerTypeMeta[provider.provider_type]?.label || provider.provider_type || '?').slice(0, 2).toUpperCase() }}
                </div>
                <div class="provider-info">
                  <div class="provider-name-row">
                    <span class="provider-name">{{ provider.name }}</span>
                    <span class="provider-chip provider-chip--type">
                      <span class="provider-chip__dot" />
                      {{ providerTypeMeta[provider.provider_type]?.label || provider.provider_type }}
                    </span>
                    <span
                      :class="['provider-chip', provider.is_enabled ? 'provider-chip--success' : 'provider-chip--muted']"
                    >
                      <span class="provider-chip__dot" />
                      {{ provider.is_enabled ? '已启用' : '已禁用' }}
                    </span>
                    <span
                      v-if="provider.has_api_key"
                      class="provider-chip provider-chip--success"
                    >
                      <span class="provider-chip__dot" />
                      已配置密钥
                    </span>
                    <span
                      v-else
                      class="provider-chip provider-chip--danger"
                    >
                      <span class="provider-chip__dot" />
                      未配置密钥
                    </span>
                  </div>
                  <div class="provider-meta">
                    <span class="provider-meta-row">
                      <span class="provider-meta-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
                          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
                        </svg>
                      </span>
                      <span class="provider-meta-label">接口</span>
                      <span class="provider-meta-value">{{ provider.api_base || '未设置' }}</span>
                    </span>
                    <span class="provider-meta-row">
                      <span class="provider-meta-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
                          <path d="M12 2 4 6v6c0 5 3.5 9.5 8 10 4.5-.5 8-5 8-10V6l-8-4z" />
                        </svg>
                      </span>
                      <span class="provider-meta-label">模型</span>
                      <span class="provider-meta-value">{{ provider.default_model || '未设置默认模型' }}</span>
                    </span>
                  </div>
                </div>
                <div class="provider-actions">
                  <ElButton
                    size="small"
                    :loading="testingProviderId === provider.id"
                    @click="handleTestConnection(provider.id)"
                  >
                    测试连接
                  </ElButton>
                  <ElButton size="small" @click="openEditModal(provider)">编辑</ElButton>
                  <ElPopconfirm
                    title="确定要删除此提供商吗？"
                    @confirm="handleDelete(provider.id)"
                  >
                    <template #reference>
                      <ElButton size="small" type="danger" plain>删除</ElButton>
                    </template>
                  </ElPopconfirm>
                </div>
              </div>

              <div
                v-if="testingProviderId === provider.id"
                class="test-status test-loading"
              >
                <span class="test-status__dot" />
                <span>正在测试连接...</span>
              </div>
              <div
                v-else-if="testResult && testResultProviderId === provider.id"
                :class="['test-status', testResult.success ? 'test-success' : 'test-fail']"
              >
                <span class="test-status__dot" />
                <span v-if="testResult.success">连接成功 — 延迟 {{ testResult.latency_ms ?? '—' }}ms{{ testResult.model_used ? '，模型: ' + testResult.model_used : '' }}</span>
                <span v-else>连接失败: {{ testResult.message || '未知错误' }}</span>
              </div>
            </div>
          </div>
        </ElTabPane>

        <ElTabPane label="缓存配置" name="cache">
          <div class="tab-header tab-header--stacked">
            <div>
              <h2 class="tab-section-title">
                <span class="tab-section-title-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 12a9 9 0 1 1-9-9c2.39 0 4.68.94 6.36 2.64" />
                    <path d="M21 4v5h-5" />
                  </svg>
                </span>
                缓存配置
              </h2>
              <p class="section-caption">通过缓存来减少token消耗，已命中文本会直接进行替换</p>
            </div>
          </div>

          <div class="settings-card">
            <ElForm label-width="180px" class="settings-form" label-position="left">
              <ElFormItem label="缓存自动清理">
                <div class="form-item-row">
                  <ElSwitch v-model="cacheForm.autoClean" disabled />
                  <span class="form-hint">当前版本暂未提供独立持久化配置；实际缓存启用与范围由翻译配置页控制。</span>
                </div>
              </ElFormItem>
              <ElFormItem label="缓存最大条目数">
                <ElInputNumber
                  v-model="cacheForm.maxEntries"
                  :min="100"
                  :max="100000"
                  :step="100"
                  disabled
                />
              </ElFormItem>
              <ElFormItem label="缓存命中策略">
                <ElSelect v-model="cacheForm.hitStrategy" style="width: 240px" disabled>
                  <ElOption value="strict" label="严格模式（仅相同版本）" />
                  <ElOption value="standard" label="标准模式（同整合包）" />
                  <ElOption value="loose" label="宽松模式（跨整合包）" />
                </ElSelect>
              </ElFormItem>
            </ElForm>
          </div>

          <div v-loading="store.cacheStatsLoading" class="settings-card">
            <div class="cache-stats-grid">
              <div class="cache-stat-item">
                <span class="cache-stat-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
                    <ellipse cx="12" cy="5" rx="9" ry="3" />
                    <path d="M3 5v6c0 1.66 4.03 3 9 3s9-1.34 9-3V5" />
                    <path d="M3 11v6c0 1.66 4.03 3 9 3s9-1.34 9-3v-6" />
                  </svg>
                </span>
                <div class="cache-stat-body">
                  <span class="stat-label-text">缓存条目</span>
                  <span class="stat-value">{{ cacheStats.entries.toLocaleString() }} 条</span>
                </div>
              </div>
              <div class="cache-stat-item">
                <span class="cache-stat-icon cache-stat-icon--success" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                    <polyline points="22 4 12 14.01 9 11.01" />
                  </svg>
                </span>
                <div class="cache-stat-body">
                  <span class="stat-label-text">累计命中</span>
                  <span class="stat-value stat-green">{{ cacheStats.hits.toLocaleString() }} 次</span>
                </div>
              </div>
              <div class="cache-stat-item">
                <span class="cache-stat-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <polyline points="12 6 12 12 16 14" />
                  </svg>
                </span>
                <div class="cache-stat-body">
                  <span class="stat-label-text">最近命中</span>
                  <span class="stat-value stat-value--sm">{{ formatDateTime(cacheStats.last_used_at) }}</span>
                </div>
              </div>
              <div class="cache-stat-item">
                <span class="cache-stat-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 20h9" />
                    <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
                  </svg>
                </span>
                <div class="cache-stat-body">
                  <span class="stat-label-text">最近写入</span>
                  <span class="stat-value stat-value--sm">{{ formatDateTime(cacheStats.last_created_at) }}</span>
                </div>
              </div>
            </div>

            <div class="cache-breakdown-grid">
              <div class="cache-breakdown-card">
                <div class="cache-breakdown-title">作用域分布</div>
                <div class="cache-breakdown-list">
                  <div v-for="entry in cacheStatsScopeEntries" :key="entry.key" class="cache-breakdown-row">
                    <span class="cache-breakdown-row__label">{{ entry.label }}</span>
                    <span class="cache-breakdown-row__value">{{ entry.value.toLocaleString() }}</span>
                    <div class="cache-breakdown-row__bar">
                      <span
                        class="cache-breakdown-row__bar-fill"
                        :style="{ width: cacheStatsScopeMax > 0 ? `${(entry.value / cacheStatsScopeMax) * 100}%` : '0%' }"
                      />
                    </div>
                  </div>
                </div>
              </div>

              <div class="cache-breakdown-card">
                <div class="cache-breakdown-title">目标语言分布</div>
                <div v-if="cacheStatsLanguageEntries.length > 0" class="cache-breakdown-list">
                  <div v-for="entry in cacheStatsLanguageEntries.slice(0, 6)" :key="entry.language" class="cache-breakdown-row">
                    <span class="cache-breakdown-row__label">{{ entry.language }}</span>
                    <span class="cache-breakdown-row__value">{{ entry.value.toLocaleString() }}</span>
                    <div class="cache-breakdown-row__bar">
                      <span
                        class="cache-breakdown-row__bar-fill"
                        :style="{ width: cacheStatsLanguageMax > 0 ? `${(entry.value / cacheStatsLanguageMax) * 100}%` : '0%' }"
                      />
                    </div>
                  </div>
                </div>
                <div v-else class="cache-breakdown-empty">暂无语言分布数据</div>
              </div>
            </div>
          </div>

          <div class="danger-card">
            <div class="danger-content">
              <div class="danger-info">
                <span class="danger-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M3 6h18" />
                    <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    <path d="M19 6 18 20a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                    <line x1="10" y1="11" x2="10" y2="17" />
                    <line x1="14" y1="11" x2="14" y2="17" />
                  </svg>
                </span>
                <div class="danger-text">
                  <span class="danger-label">清空所有缓存</span>
                  <span class="danger-desc">删除所有翻译缓存数据，此操作不可撤销</span>
                </div>
              </div>
              <ElPopconfirm
                title="确定要清空所有翻译缓存吗？此操作不可撤销。"
                @confirm="clearAllCache"
              >
                <template #reference>
                  <ElButton type="danger" :loading="store.cacheClearing">清空所有缓存</ElButton>
                </template>
              </ElPopconfirm>
            </div>
          </div>
        </ElTabPane>
      </ElTabs>

    </div>
  </component>

  <ElDialog
    v-model="modalVisible"
    :title="modalTitle"
    width="520px"
    :close-on-click-modal="true"
    append-to-body
    class="provider-dialog"
    align-center
  >
    <ElForm label-width="110px" class="settings-form" label-position="left">
      <ElFormItem label="名称" required>
        <ElInput v-model="form.name" placeholder="输入提供商名称" />
      </ElFormItem>
      <ElFormItem label="提供商类型">
        <ElSelect
          v-model="form.provider_type"
          style="width: 100%"
          @change="onProviderTypeChange"
        >
          <ElOption value="openai" label="OpenAI" />
          <ElOption value="anthropic" label="Anthropic" />
          <ElOption value="deepseek" label="DeepSeek" />
          <ElOption value="qwen" label="通义千问" />
          <ElOption value="zhipu" label="智谱GLM" />
          <ElOption value="ollama" label="Ollama" />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="API Key">
        <ElInput
          v-model="form.api_key"
          type="password"
          show-password
          :placeholder="editingProviderId !== null ? apiKeyPlaceholder : '输入 API Key'"
          @input="onApiKeyInput"
        />
      </ElFormItem>
      <ElFormItem label="API 基础地址">
        <ElInput v-model="form.api_base" placeholder="例如 https://api.openai.com/v1" @input="onApiBaseInput" />
      </ElFormItem>
      <ElFormItem label="模型名称">
        <div class="provider-model-control">
          <div class="provider-model-toolbar">
            <ElButton size="small" :loading="loadingModels" @click="handleLoadModels">获取模型</ElButton>
            <span class="provider-model-hint">{{ modelFetchHint }}</span>
          </div>
          <ElSelect
            v-model="form.default_model"
            class="provider-model-select"
            placeholder="例如 gpt-4o"
            clearable
            filterable
            allow-create
            default-first-option
            :reserve-keyword="false"
            :loading="loadingModels"
            no-data-text="暂无模型，可点击“获取模型”或直接输入"
            @change="modalTestResult = null"
          >
            <ElOption
              v-for="model in modelOptions"
              :key="model.id"
              :value="model.id"
              :label="model.name || model.id"
            >
              <div class="provider-model-option">
                <span class="provider-model-option__id">{{ model.id }}</span>
                <span v-if="model.owned_by" class="provider-model-option__owner">{{ model.owned_by }}</span>
              </div>
            </ElOption>
          </ElSelect>
          <div v-if="modelsError" class="provider-model-error">
            {{ modelsError }}，仍可直接输入任意模型名称
          </div>
        </div>
      </ElFormItem>
      <ElFormItem label="是否启用">
        <ElSwitch v-model="form.is_enabled" />
      </ElFormItem>
    </ElForm>
    <div v-if="modalTestResult" :class="['test-status', modalTestResult.success ? 'test-success' : 'test-fail']">
      <span v-if="modalTestResult.success">连接成功 — 延迟 {{ modalTestResult.latency_ms ?? '—' }}ms{{ modalTestResult.model_used ? '，模型: ' + modalTestResult.model_used : '' }}</span>
      <span v-else>连接失败: {{ modalTestResult.message || '未知错误' }}</span>
    </div>
    <template #footer>
      <ElButton @click="modalVisible = false">取消</ElButton>
      <ElButton :loading="testingModalProvider" @click="handleModalTestConnection">测试连接</ElButton>
      <ElButton type="primary" :loading="savingProvider" @click="handleSubmit">保存</ElButton>
    </template>
  </ElDialog>
</template>

<style lang="scss" scoped>
.settings-view {
  max-width: 1040px;
  margin: 0 auto;
  padding: 28px 24px 80px;
}

.settings-view--dialog {
  max-width: none;
  margin: 0;
  padding: 0 0 4px;
}

// =====================================================================
//  HERO
// =====================================================================
.settings-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: var(--notion-spacing-lg);
  margin-bottom: var(--notion-spacing-xl);

  @media (max-width: 900px) {
    grid-template-columns: 1fr;
  }
}

.settings-hero-copy {
  position: relative;
  border-radius: var(--notion-rounded-xl);
  padding: var(--notion-spacing-xl) var(--notion-spacing-xl);
  display: flex;
  flex-direction: column;
  gap: 10px;
  background:
    linear-gradient(135deg, rgba(15, 108, 189, 0.06) 0%, rgba(15, 108, 189, 0) 55%),
    var(--fluent-surface-2);
  border: 1px solid var(--notion-hairline-soft);
  box-shadow: var(--notion-shadow-subtle);
  overflow: hidden;

  &::after {
    content: '';
    position: absolute;
    inset: auto -40px -60px auto;
    width: 220px;
    height: 220px;
    border-radius: 50%;
    background: radial-gradient(circle, var(--fluent-accent-subtle), transparent 65%);
    pointer-events: none;
  }
}

.settings-hero-meta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  position: relative;
  z-index: 1;
}

.settings-hero-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--notion-rounded-sm);
  background: var(--fluent-accent-subtle);
  color: var(--fluent-accent);
}

.settings-kicker {
  font-size: var(--notion-font-size-micro);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--fluent-accent);
  font-weight: 600;
}

.page-title {
  font-size: var(--notion-font-size-h2);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0;
  line-height: var(--notion-line-height-h2);
  letter-spacing: var(--notion-ls-h2);
  position: relative;
  z-index: 1;
}

.settings-subtitle {
  margin: 0;
  color: var(--notion-slate);
  font-size: var(--notion-font-size-body);
  line-height: var(--notion-line-height-body);
  max-width: 640px;
  position: relative;
  z-index: 1;
}

.settings-summary-card {
  border-radius: var(--notion-rounded-xl);
  padding: var(--notion-spacing-lg) var(--notion-spacing-xl);
  display: flex;
  align-items: center;
  gap: 14px;
  background:
    linear-gradient(135deg, var(--fluent-accent) 0%, var(--fluent-accent-pressed) 100%);
  border: 1px solid transparent;
  box-shadow: 0 10px 24px rgba(15, 108, 189, 0.22), var(--notion-shadow-subtle);
  color: var(--notion-on-primary);
  position: relative;
  overflow: hidden;

  &::after {
    content: '';
    position: absolute;
    right: -30px;
    bottom: -30px;
    width: 120px;
    height: 120px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.12);
    pointer-events: none;
  }
}

.summary-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--notion-rounded-md);
  background: rgba(255, 255, 255, 0.18);
  flex-shrink: 0;
}

.summary-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  z-index: 1;
}

.summary-label {
  font-size: var(--notion-font-size-caption);
  color: rgba(255, 255, 255, 0.82);
  font-weight: 500;
}

.summary-value {
  font-size: 28px;
  line-height: 1.05;
  font-weight: 600;
  color: var(--notion-on-primary);
  letter-spacing: -0.01em;
}

.summary-hint {
  font-size: var(--notion-font-size-caption);
  color: rgba(255, 255, 255, 0.78);
  line-height: 1.4;
}

.error-alert {
  margin-bottom: var(--notion-spacing-md);
  border-radius: var(--notion-rounded-md);
}

.tab-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: var(--notion-spacing-lg);

  @media (max-width: 640px) {
    flex-direction: column;
    align-items: stretch;
  }
}

.tab-header--stacked {
  margin-bottom: var(--notion-spacing-md);
}

.tab-section-title {
  font-size: var(--notion-font-size-h4);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0 0 6px;
  letter-spacing: -0.01em;
  display: flex;
  align-items: center;
  gap: 10px;
}

.tab-section-title-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--notion-rounded-sm);
  background: var(--fluent-accent-subtle);
  color: var(--fluent-accent);
  flex-shrink: 0;
}

.section-caption {
  margin: 0;
  color: var(--notion-steel);
  font-size: var(--notion-font-size-caption);
}

.stats-title {
  margin-top: var(--notion-spacing-xl);
}

.danger-title {
  margin-top: var(--notion-spacing-xl);
  color: var(--notion-semantic-error);
}

.provider-empty {
  margin: 48px 0;
  border-radius: var(--notion-rounded-lg);
}

.provider-list {
  display: flex;
  flex-direction: column;
  gap: var(--notion-spacing-sm);
}

.provider-card {
  position: relative;
  border-radius: var(--notion-rounded-lg);
  padding: var(--notion-spacing-lg) var(--notion-spacing-xl);
  background: var(--fluent-surface-2);
  border: 1px solid var(--notion-hairline-soft);
  box-shadow: var(--notion-shadow-subtle);
  transition:
    border-color var(--notion-transition-fast),
    box-shadow var(--notion-transition-fast),
    transform var(--notion-transition-fast);

  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 16px;
    bottom: 16px;
    width: 3px;
    border-radius: 0 3px 3px 0;
    background: linear-gradient(180deg, var(--fluent-accent), var(--fluent-accent-pressed));
    opacity: 0;
    transition: opacity var(--notion-transition-fast);
  }

  &:hover {
    border-color: var(--notion-hairline);
    box-shadow: var(--notion-shadow-card);

    &::before {
      opacity: 1;
    }
  }
}

.cache-breakdown-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--notion-spacing-md);
  margin-top: var(--notion-spacing-md);

  @media (max-width: 720px) {
    grid-template-columns: 1fr;
  }
}

.cache-breakdown-card {
  border-radius: var(--notion-rounded-md);
  border: 1px solid var(--notion-hairline-soft);
  background: var(--fluent-surface-3);
  padding: var(--notion-spacing-md);
}

.cache-breakdown-title {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 600;
  color: var(--notion-ink);
  margin-bottom: var(--notion-spacing-sm);
}

.cache-breakdown-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cache-breakdown-row {
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-rows: auto auto;
  column-gap: var(--notion-spacing-md);
  row-gap: 4px;
  color: var(--notion-slate);
  font-size: var(--notion-font-size-body-sm);
  align-items: center;
}

.cache-breakdown-row__label {
  color: var(--notion-ink);
  font-weight: 500;
}

.cache-breakdown-row__value {
  color: var(--notion-ink);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  font-size: var(--notion-font-size-body-sm);
}

.cache-breakdown-row__bar {
  grid-column: 1 / -1;
  height: 4px;
  background: var(--fluent-bg-canvas-subtle);
  border-radius: var(--notion-rounded-full);
  overflow: hidden;
}

.cache-breakdown-row__bar-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--fluent-accent), var(--fluent-accent-pressed));
  border-radius: inherit;
  transition: width var(--notion-transition-normal);
}

.cache-breakdown-empty {
  color: var(--notion-steel);
  font-size: var(--notion-font-size-caption);
  text-align: center;
  padding: 12px 0;
}

.provider-card-main {
  display: flex;
  align-items: flex-start;
  gap: 14px;

  @media (max-width: 820px) {
    flex-wrap: wrap;
  }
}

.provider-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--notion-rounded-sm);
  font-size: 13px;
  font-weight: 700;
  color: var(--notion-on-primary);
  background: linear-gradient(135deg, var(--fluent-accent), var(--fluent-accent-pressed));
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.15);
  flex-shrink: 0;
  letter-spacing: 0.02em;

  &[data-type='openai'] {
    background: linear-gradient(135deg, #10a37f, #0c8a6a);
  }
  &[data-type='anthropic'] {
    background: linear-gradient(135deg, #c75c11, #8a3f08);
  }
  &[data-type='deepseek'] {
    background: linear-gradient(135deg, #0f6cbd, #08467d);
  }
  &[data-type='qwen'] {
    background: linear-gradient(135deg, #6b4fd3, #3f2b85);
  }
  &[data-type='zhipu'] {
    background: linear-gradient(135deg, #cc5da8, #8e3b72);
  }
  &[data-type='ollama'] {
    background: linear-gradient(135deg, #475569, #1e293b);
  }
}

.provider-info {
  flex: 1;
  min-width: 0;
}

.provider-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.provider-name {
  font-size: var(--notion-font-size-h5);
  font-weight: 600;
  color: var(--notion-ink);
  letter-spacing: -0.01em;
  margin-right: 4px;
}

.provider-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--notion-font-size-caption);
  line-height: 1;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: var(--notion-rounded-full);
  border: 1px solid var(--notion-hairline-soft);
  background: var(--fluent-surface-3);
  color: var(--notion-slate);
  flex-shrink: 0;
}

.provider-chip__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}

.provider-chip--type {
  color: var(--fluent-accent);
  background: var(--fluent-accent-subtle);
  border-color: transparent;
}

.provider-chip--success {
  color: var(--notion-semantic-success);
  background: var(--fluent-surface-success-subtle);
  border-color: transparent;
}

.provider-chip--muted {
  color: var(--notion-stone);
  background: var(--fluent-bg-canvas-subtle);
  border-color: transparent;
}

.provider-chip--danger {
  color: var(--notion-semantic-error);
  background: var(--fluent-surface-danger-subtle);
  border-color: transparent;
}

.provider-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.provider-meta-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--notion-font-size-body-sm);
  min-width: 0;
}

.provider-meta-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--notion-muted);
  flex-shrink: 0;
}

.provider-meta-label {
  color: var(--notion-slate);
  font-weight: 500;
}

.provider-meta-value {
  color: var(--notion-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex: 1;
  font-variant-numeric: tabular-nums;
}

.provider-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  flex-wrap: wrap;
  margin-left: auto;
}

.test-status {
  margin-top: var(--notion-spacing-md);
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--notion-font-size-body-sm);
  padding: 8px 12px;
  border-radius: var(--notion-rounded-sm);
  border: 1px solid transparent;
}

.test-status__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}

.test-loading {
  color: var(--notion-slate);
  background-color: var(--fluent-surface-inset);
  border-color: var(--notion-hairline-soft);
}

.test-success {
  color: var(--notion-semantic-success);
  background-color: var(--fluent-surface-success-subtle);
  border-color: rgba(16, 124, 16, 0.2);
}

.test-fail {
  color: var(--notion-semantic-error);
  background-color: var(--fluent-surface-danger-subtle);
  border-color: rgba(196, 43, 28, 0.2);
}

.settings-card {
  margin: 5px auto;
  position: relative;
  border-radius: var(--notion-rounded-xl);
  padding: var(--notion-spacing-xl);
  background: var(--fluent-surface-2);
  border: 1px solid var(--notion-hairline-soft);
  box-shadow: var(--notion-shadow-subtle);
}

.settings-form {
  :deep(.el-form-item) {
    margin-bottom: var(--notion-spacing-lg);
  }

  :deep(.el-form-item:last-child) {
    margin-bottom: 0;
  }

  :deep(.el-form-item__label) {
    color: var(--notion-slate);
    font-size: var(--notion-font-size-body-sm);
    font-weight: 500;
    line-height: var(--notion-line-height-body-sm);
  }
}

.form-item-row {
  display: flex;
  align-items: center;
  gap: var(--notion-spacing-sm);
}

.general-inline-field {
  display: flex;
  align-items: center;
  gap: var(--notion-spacing-sm);
  flex-wrap: wrap;
}

.general-field-stack {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  width: min(100%, 560px);
}

.general-wide-input {
  width: 100%;
}

.settings-actions-row {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
  margin-top: var(--notion-spacing-xl);
  padding-top: var(--notion-spacing-md);
  border-top: 1px solid var(--notion-hairline-soft);
}

.form-hint {
  font-size: var(--notion-font-size-caption);
  color: var(--notion-steel);
  line-height: var(--notion-line-height-caption);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.provider-model-control {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  width: 100%;
}

.provider-model-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.provider-model-hint {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-steel);
  line-height: var(--notion-line-height-caption);
}

.provider-model-select {
  width: 100%;
}

.provider-model-option {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.provider-model-option__id {
  font-weight: 500;
  color: var(--notion-ink);
  min-width: 0;
}

.provider-model-option__owner {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-steel);
  flex-shrink: 0;
}

.provider-model-error {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-semantic-warning);
  line-height: var(--notion-line-height-caption);
  word-break: break-word;
}

.cache-stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--notion-spacing-md);

  @media (max-width: 720px) {
    grid-template-columns: repeat(2, 1fr);
  }
}

.cache-stat-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: var(--notion-spacing-md);
  border-radius: var(--notion-rounded-md);
  background: var(--fluent-surface-3);
  border: 1px solid var(--notion-hairline-soft);
  transition:
    border-color var(--notion-transition-fast),
    background-color var(--notion-transition-fast);
}

.cache-stat-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--notion-rounded-sm);
  background: var(--fluent-accent-subtle);
  color: var(--fluent-accent);
  flex-shrink: 0;
}

.cache-stat-icon--success {
  background: var(--fluent-surface-success-subtle);
  color: var(--notion-semantic-success);
}

.cache-stat-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.stat-label-text {
  font-size: var(--notion-font-size-caption);
  color: var(--notion-slate);
  font-weight: 500;
}

.stat-value {
  font-size: var(--notion-font-size-h5);
  font-weight: 600;
  color: var(--notion-ink);
  letter-spacing: -0.01em;
  line-height: 1.2;
}

.stat-value--sm {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 500;
  line-height: 1.4;
  letter-spacing: 0;
}

.stat-green {
  color: var(--notion-semantic-success);
}

.stat-orange {
  color: var(--notion-semantic-warning);
}

.danger-card {
  margin-top: 10px;
  position: relative;
  border-radius: var(--notion-rounded-xl);
  padding: var(--notion-spacing-lg) var(--notion-spacing-xl);
  background: var(--fluent-surface-danger-subtle);
  border: 1px solid rgba(196, 43, 28, 0.28);
  box-shadow: var(--notion-shadow-subtle);
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background: var(--notion-semantic-error);
  }
}

.danger-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;

  @media (max-width: 640px) {
    flex-direction: column;
    align-items: flex-start;
  }
}

.danger-info {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.danger-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--notion-rounded-sm);
  background: rgba(196, 43, 28, 0.12);
  color: var(--notion-semantic-error);
  flex-shrink: 0;
}

.danger-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.danger-label {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 600;
  color: var(--notion-ink);
}

.danger-desc {
  font-size: var(--notion-font-size-caption);
  color: var(--notion-slate);
  line-height: 1.45;
}

.settings-divider {
  margin: var(--notion-spacing-xxl) 0 28px;
  border-color: var(--notion-hairline);
}

:deep(.provider-dialog) {
  .el-dialog {
    border-radius: var(--notion-rounded-xl);
    background-color: var(--fluent-surface-3);
    border: 1px solid var(--notion-hairline);
    box-shadow: var(--notion-shadow-modal);
    overflow: hidden;
  }

  .el-dialog__header {
    padding: var(--notion-spacing-lg) var(--notion-spacing-xl) var(--notion-spacing-md);
  }

  .el-dialog__title {
    font-size: var(--notion-font-size-h5);
    font-weight: 600;
    color: var(--notion-ink);
  }

  .el-dialog__body {
    padding: var(--notion-spacing-md) var(--notion-spacing-xl) var(--notion-spacing-lg);
  }

  .el-dialog__footer {
    padding: var(--notion-spacing-md) var(--notion-spacing-xl) var(--notion-spacing-lg);
    border-top: 1px solid var(--notion-hairline-soft);
    background: var(--fluent-bg-canvas-subtle);
  }
}

:deep(.settings-dialog) {
  .el-dialog {
    border-radius: var(--notion-rounded-xl);
    background-color: var(--fluent-surface-3);
    border: 1px solid var(--notion-hairline);
    box-shadow: var(--notion-shadow-modal);
    overflow: hidden;
  }

  .el-dialog__header {
    padding: var(--notion-spacing-lg) var(--notion-spacing-xl) var(--notion-spacing-md);
  }

  .el-dialog__title {
    font-size: var(--notion-font-size-h4);
    font-weight: 600;
    color: var(--notion-ink);
    letter-spacing: -0.01em;
  }

  .el-dialog__body {
    padding: var(--notion-spacing-md) var(--notion-spacing-xl) var(--notion-spacing-lg);
    max-height: 65vh;
    overflow-y: auto;
  }
}

// =====================================================================
//  Dark mode refinements are applied in a non-scoped style block below.
// =====================================================================
</style>

<style lang="scss">
// =====================================================================
//  Global dark-mode polish for the Settings page.
//  (Kept non-scoped so html.dark selectors apply cleanly.)
// =====================================================================
html.dark .settings-view {
  .settings-hero-copy::after {
    background: radial-gradient(circle, rgba(76, 194, 255, 0.18), transparent 65%);
  }

  .settings-summary-card {
    box-shadow:
      0 14px 32px rgba(0, 0, 0, 0.36),
      0 4px 10px rgba(0, 0, 0, 0.2);
  }

  .provider-avatar {
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
  }

  .cache-stat-item {
    background: var(--fluent-bg-canvas-subtle);
  }

  .provider-notice {
    background: rgba(76, 194, 255, 0.08);
  }
}
</style>
