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
  ElTag,
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
const cacheStatsLanguageEntries = computed(() => {
  const source = cacheStats.value?.by_target_language || {}
  return Object.entries(source)
    .map(([language, value]) => ({ language, value: Number(value || 0) }))
    .sort((a, b) => b.value - a.value)
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
          <span class="settings-kicker">系统设置</span>
          <h1 class="page-title">统一管理运行环境、提供商与缓存策略</h1>
          <p class="settings-subtitle">保持桌面工作区配置集中、状态清晰，并减少干扰性视觉元素。</p>
        </div>
        <div class="settings-summary-card">
          <span class="summary-label">已配置提供商</span>
          <span class="summary-value">{{ store.aiProviders.length }}</span>
          <span class="summary-hint">可在此维护默认模型与连接状态</span>
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

      <ElTabs v-model="activeTab" class="settings-tabs">
        <ElTabPane label="通用设置" name="general">
          <div class="tab-header tab-header--stacked">
            <div>
              <h2 class="tab-section-title">通用设置</h2>
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
              <h2 class="tab-section-title">AI 提供商配置</h2>
              <p class="section-caption">为翻译工作流准备稳定的连接、模型与启用状态。</p>
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
                <div class="provider-info">
                  <div class="provider-name-row">
                    <span class="provider-name">{{ provider.name }}</span>
                    <ElTag
                      :type="providerTypeTagType[provider.provider_type] || 'info'"
                      size="small"
                      class="provider-type-tag"
                    >
                      {{ providerTypeMeta[provider.provider_type]?.label || provider.provider_type }}
                    </ElTag>
                    <ElTag
                      :type="provider.is_enabled ? 'success' : 'info'"
                      size="small"
                      class="provider-status-tag"
                    >
                      {{ provider.is_enabled ? '已启用' : '已禁用' }}
                    </ElTag>
                    <ElTag
                      v-if="provider.has_api_key"
                      type="success"
                      size="small"
                      effect="light"
                    >
                      已配置密钥
                    </ElTag>
                    <ElTag
                      v-else
                      type="danger"
                      size="small"
                      effect="light"
                    >
                      未配置密钥
                    </ElTag>
                  </div>
                  <div class="provider-meta">
                    <span class="provider-url">{{ provider.api_base || '未设置' }}</span>
                    <span class="provider-model">{{ provider.default_model || '未设置默认模型' }}</span>
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
                      <ElButton size="small" type="danger">删除</ElButton>
                    </template>
                  </ElPopconfirm>
                </div>
              </div>

              <div
                v-if="testingProviderId === provider.id"
                class="test-status test-loading"
              >
                <span>正在测试连接...</span>
              </div>
              <div
                v-else-if="testResult && testResultProviderId === provider.id"
                :class="['test-status', testResult.success ? 'test-success' : 'test-fail']"
              >
                <span v-if="testResult.success">连接成功 — 延迟 {{ testResult.latency_ms ?? '—' }}ms{{ testResult.model_used ? '，模型: ' + testResult.model_used : '' }}</span>
                <span v-else>连接失败: {{ testResult.message || '未知错误' }}</span>
              </div>
            </div>
          </div>
        </ElTabPane>

        <ElTabPane label="缓存配置" name="cache">
          <div class="tab-header tab-header--stacked">
            <div>
              <h2 class="tab-section-title">缓存配置</h2>
              <p class="section-caption">当前页已接入后端真实缓存数据；下方策略项仍作为展示占位，不影响实际翻译时由配置页传入的缓存参数。</p>
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

          <h2 class="tab-section-title stats-title">缓存统计</h2>
          <div v-loading="store.cacheStatsLoading" class="settings-card">
            <div class="cache-stats-grid">
              <div class="cache-stat-item">
                <span class="stat-label-text">缓存条目</span>
                <span class="stat-value">{{ cacheStats.entries.toLocaleString() }} 条</span>
              </div>
              <div class="cache-stat-item">
                <span class="stat-label-text">累计命中</span>
                <span class="stat-value stat-green">{{ cacheStats.hits.toLocaleString() }} 次</span>
              </div>
              <div class="cache-stat-item">
                <span class="stat-label-text">最近命中</span>
                <span class="stat-value">{{ formatDateTime(cacheStats.last_used_at) }}</span>
              </div>
              <div class="cache-stat-item">
                <span class="stat-label-text">最近写入</span>
                <span class="stat-value">{{ formatDateTime(cacheStats.last_created_at) }}</span>
              </div>
            </div>

            <div class="cache-breakdown-grid">
              <div class="cache-breakdown-card">
                <div class="cache-breakdown-title">作用域分布</div>
                <div class="cache-breakdown-list">
                  <div v-for="entry in cacheStatsScopeEntries" :key="entry.key" class="cache-breakdown-row">
                    <span>{{ entry.label }}</span>
                    <span>{{ entry.value.toLocaleString() }}</span>
                  </div>
                </div>
              </div>

              <div class="cache-breakdown-card">
                <div class="cache-breakdown-title">目标语言分布</div>
                <div v-if="cacheStatsLanguageEntries.length > 0" class="cache-breakdown-list">
                  <div v-for="entry in cacheStatsLanguageEntries.slice(0, 6)" :key="entry.language" class="cache-breakdown-row">
                    <span>{{ entry.language }}</span>
                    <span>{{ entry.value.toLocaleString() }}</span>
                  </div>
                </div>
                <div v-else class="cache-breakdown-empty">暂无语言分布数据</div>
              </div>
            </div>
          </div>

          <h2 class="tab-section-title danger-title">危险操作</h2>
          <div class="danger-card">
            <div class="danger-content">
              <div class="danger-info">
                <span class="danger-label">清空所有缓存</span>
                <span class="danger-desc">删除所有翻译缓存数据，此操作不可撤销</span>
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
  padding: 24px 24px 80px;
}

.settings-view--dialog {
  max-width: none;
  margin: 0;
  padding: 0 0 4px;
}

.settings-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 240px;
  gap: $spacing-lg;
  margin-bottom: $spacing-lg;

  @media (max-width: 900px) {
    grid-template-columns: 1fr;
  }
}

.settings-hero-copy,
.settings-summary-card,
.settings-card,
.provider-card,
.danger-card {
  background: var(--fluent-surface-2);
  border: 1px solid var(--notion-hairline-soft);
  box-shadow: var(--notion-shadow-subtle);
}

.settings-hero-copy {
  border-radius: $rounded-xl;
  padding: $spacing-xl;
  display: flex;
  flex-direction: column;
  gap: $spacing-xs;
}

.settings-kicker {
  font-size: $font-size-micro-uppercase;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--fluent-accent);
  font-weight: $font-weight-semibold;
}

.page-title {
  font-size: var(--notion-font-size-h3);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0;
  line-height: var(--notion-line-height-h3);
}

.settings-subtitle {
  margin: 0;
  color: var(--notion-steel);
  font-size: var(--notion-font-size-body-sm);
  line-height: var(--notion-line-height-body-sm);
}

.settings-summary-card {
  border-radius: $rounded-xl;
  padding: $spacing-lg;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  background: linear-gradient(180deg, var(--fluent-surface-3), var(--fluent-surface-2));
}

.summary-label {
  font-size: $font-size-caption;
  color: var(--notion-steel);
}

.summary-value {
  font-size: 28px;
  line-height: 1;
  font-weight: $font-weight-semibold;
  color: var(--notion-ink);
}

.summary-hint {
  font-size: $font-size-caption;
  color: var(--notion-steel);
}

.error-alert {
  margin-bottom: var(--notion-spacing-md);
}

.settings-tabs {
  margin-top: var(--notion-spacing-xs);

  :deep(.el-tabs__header) {
    margin: 0 0 var(--notion-spacing-lg);
  }

  :deep(.el-tabs__nav-wrap::after) {
    height: 1px;
    background-color: var(--notion-hairline);
  }

  :deep(.el-tabs__item) {
    font-size: var(--notion-font-size-body-sm);
    font-weight: 500;
    color: var(--notion-steel);
    padding: 10px var(--notion-spacing-md);
    height: auto;
    line-height: var(--notion-line-height-body-sm);
    transition: color var(--notion-transition-fast), background-color var(--notion-transition-fast);
    border-radius: var(--notion-rounded-sm);

    &:hover {
      color: var(--notion-ink);
      background: var(--fluent-surface-accent-subtle);
    }

    &.is-active {
      color: var(--notion-ink);
      font-weight: 600;
    }
  }

  :deep(.el-tabs__active-bar) {
    height: 2px;
    background-color: var(--fluent-accent);
  }
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
  font-size: var(--notion-font-size-h5);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0 0 6px;
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
}

.provider-list {
  display: flex;
  flex-direction: column;
  gap: var(--notion-spacing-sm);
}

.provider-card {
  border-radius: var(--notion-rounded-lg);
  padding: var(--notion-spacing-lg);
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
  gap: 10px;
}

.cache-breakdown-row {
  display: flex;
  justify-content: space-between;
  gap: var(--notion-spacing-md);
  color: var(--notion-steel);
  font-size: var(--notion-font-size-body-sm);
}

.cache-breakdown-empty {
  color: var(--notion-steel);
  font-size: var(--notion-font-size-caption);
}

.provider-card-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;

  @media (max-width: 820px) {
    flex-direction: column;
  }
}

.provider-info {
  flex: 1;
  min-width: 0;
}

.provider-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.provider-name {
  font-size: var(--notion-font-size-body);
  font-weight: 600;
  color: var(--notion-ink);
}

.provider-type-tag,
.provider-status-tag {
  flex-shrink: 0;
}

.provider-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.provider-url,
.provider-model {
  font-size: var(--notion-font-size-caption);
  color: var(--notion-steel);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.provider-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.test-status {
  margin-top: var(--notion-spacing-sm);
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--notion-font-size-caption);
  padding: 8px 12px;
  border-radius: var(--notion-rounded-sm);
}

.test-loading {
  color: var(--notion-charcoal);
  background-color: var(--fluent-surface-inset);
}

.test-success {
  color: var(--notion-semantic-success);
  background-color: var(--fluent-surface-success-subtle);
}

.test-fail {
  color: var(--notion-semantic-error);
  background-color: var(--fluent-surface-danger-subtle);
}

.settings-card {
  border-radius: var(--notion-rounded-xl);
  padding: var(--notion-spacing-xl);
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
    font-weight: 400;
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
  margin-top: var(--notion-spacing-sm);
}

.form-hint {
  font-size: var(--notion-font-size-caption);
  color: var(--notion-steel);
  line-height: var(--notion-line-height-caption);
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
  gap: var(--notion-spacing-xl);

  @media (max-width: 640px) {
    grid-template-columns: repeat(2, 1fr);
  }
}

.cache-stat-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.stat-label-text {
  font-size: var(--notion-font-size-caption);
  color: var(--notion-steel);
}

.stat-value {
  font-size: var(--notion-font-size-h5);
  font-weight: 600;
  color: var(--notion-ink);
}

.stat-green {
  color: var(--notion-semantic-success);
}

.stat-orange {
  color: var(--notion-semantic-warning);
}

.danger-card {
  border-radius: var(--notion-rounded-xl);
  padding: var(--notion-spacing-lg) var(--notion-spacing-xl);
  border-color: rgba(196, 43, 28, 0.24);
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
  flex-direction: column;
  gap: 4px;
}

.danger-label {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 600;
  color: var(--notion-ink);
}

.danger-desc {
  font-size: var(--notion-font-size-caption);
  color: var(--notion-steel);
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
  }

  .el-dialog__header {
    padding: var(--notion-spacing-lg) var(--notion-spacing-xl) 0;
  }

  .el-dialog__title {
    font-size: var(--notion-font-size-h5);
    font-weight: 600;
    color: var(--notion-ink);
  }

  .el-dialog__body {
    padding: var(--notion-spacing-lg) var(--notion-spacing-xl);
  }

  .el-dialog__footer {
    padding: var(--notion-spacing-md) var(--notion-spacing-xl) var(--notion-spacing-lg);
    border-top: 1px solid var(--notion-hairline);
  }
}

:deep(.settings-dialog) {
  .el-dialog {
    border-radius: var(--notion-rounded-xl);
    background-color: var(--fluent-surface-3);
    border: 1px solid var(--notion-hairline);
    box-shadow: var(--notion-shadow-modal);
  }

  .el-dialog__header {
    padding: var(--notion-spacing-lg) var(--notion-spacing-xl) 0;
  }

  .el-dialog__title {
    font-size: var(--notion-font-size-h4);
    font-weight: 600;
    color: var(--notion-ink);
  }

  .el-dialog__body {
    padding: var(--notion-spacing-md) var(--notion-spacing-xl) var(--notion-spacing-lg);
    max-height: 65vh;
    overflow-y: auto;
  }
}
</style>
