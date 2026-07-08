import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  clearCache,
  fetchAIModels,
  getAIProvider,
  getAIProviders,
  getCacheStats,
  getSettings,
  testAIConnection,
  updateAIProvider,
  updateSettings,
  createAIProvider,
  deleteAIProvider
} from '@/api/settings'
import { asBooleanSetting, toBooleanSettingString } from '@/utils/localizationDelivery'

const DEFAULT_SETTINGS = {
  translate_batch_retry_limit: '3',
  target_minecraft_root: '',
  patch_output_dir: '',
  include_i18n_update_mod: 'true',
  i18n_mod_cache_dir: ''
}

const DEFAULT_CACHE_STATS = {
  entries: 0,
  hits: 0,
  by_target_language: {},
  by_scope: {},
  last_used_at: null,
  last_created_at: null
}

function createDefaultSettings() {
  return { ...DEFAULT_SETTINGS }
}

function createDefaultCacheStats() {
  return {
    entries: 0,
    hits: 0,
    by_target_language: {},
    by_scope: { version: 0, modpack: 0, all: 0 },
    last_used_at: null,
    last_created_at: null
  }
}

function normalizeRetryLimit(value, fallback = DEFAULT_SETTINGS.translate_batch_retry_limit) {
  const parsed = Number.parseInt(String(value ?? fallback), 10)
  if (Number.isNaN(parsed)) return String(fallback)
  return String(Math.min(3, Math.max(0, parsed)))
}

function normalizeSettingsPayload(data = {}) {
  const nextSettings = { ...data }

  if (Object.prototype.hasOwnProperty.call(nextSettings, 'translate_batch_retry_limit')) {
    nextSettings.translate_batch_retry_limit = normalizeRetryLimit(nextSettings.translate_batch_retry_limit)
  }

  if (Object.prototype.hasOwnProperty.call(nextSettings, 'target_minecraft_root')) {
    nextSettings.target_minecraft_root = String(nextSettings.target_minecraft_root ?? '').trim()
  }

  if (Object.prototype.hasOwnProperty.call(nextSettings, 'patch_output_dir')) {
    nextSettings.patch_output_dir = String(nextSettings.patch_output_dir ?? '').trim()
  }

  if (Object.prototype.hasOwnProperty.call(nextSettings, 'include_i18n_update_mod')) {
    nextSettings.include_i18n_update_mod = toBooleanSettingString(
      asBooleanSetting(nextSettings.include_i18n_update_mod, false)
    )
  }

  if (Object.prototype.hasOwnProperty.call(nextSettings, 'i18n_mod_cache_dir')) {
    nextSettings.i18n_mod_cache_dir = String(nextSettings.i18n_mod_cache_dir ?? '').trim()
  }

  return nextSettings
}

function normalizeCacheStatsPayload(data = {}) {
  return {
    ...createDefaultCacheStats(),
    entries: Number(data?.entries || 0),
    hits: Number(data?.hits || 0),
    by_target_language: data?.by_target_language || {},
    by_scope: {
      version: Number(data?.by_scope?.version || 0),
      modpack: Number(data?.by_scope?.modpack || 0),
      all: Number(data?.by_scope?.all || 0)
    },
    last_used_at: data?.last_used_at || null,
    last_created_at: data?.last_created_at || null
  }
}

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref(createDefaultSettings())
  const aiProviders = ref([])
  const cacheStats = ref(createDefaultCacheStats())
  const loading = ref(false)
  const cacheStatsLoading = ref(false)
  const cacheClearing = ref(false)
  const error = ref(null)

  const hasSettings = computed(() => Object.keys(settings.value).length > 0)

  async function loadSettings() {
    loading.value = true
    error.value = null
    try {
      const data = await getSettings()
      settings.value = {
        ...createDefaultSettings(),
        ...(data || {})
      }
      settings.value.translate_batch_retry_limit = normalizeRetryLimit(settings.value.translate_batch_retry_limit)
      settings.value.include_i18n_update_mod = toBooleanSettingString(
        asBooleanSetting(settings.value.include_i18n_update_mod, false)
      )
      return settings.value
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '加载设置失败'
      return null
    } finally {
      loading.value = false
    }
  }

  async function saveSettings(data) {
    loading.value = true
    error.value = null
    try {
      const nextSettings = normalizeSettingsPayload(data)
      const updated = await updateSettings({ settings: nextSettings })
      settings.value = {
        ...createDefaultSettings(),
        ...settings.value,
        ...(updated || {})
      }
      settings.value.translate_batch_retry_limit = normalizeRetryLimit(settings.value.translate_batch_retry_limit)
      settings.value.include_i18n_update_mod = toBooleanSettingString(
        asBooleanSetting(settings.value.include_i18n_update_mod, false)
      )
      return settings.value
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '保存设置失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function loadCacheStats() {
    cacheStatsLoading.value = true
    error.value = null
    try {
      const data = await getCacheStats()
      cacheStats.value = normalizeCacheStatsPayload(data)
      return cacheStats.value
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '加载缓存统计失败'
      return null
    } finally {
      cacheStatsLoading.value = false
    }
  }

  async function clearAllCache() {
    cacheClearing.value = true
    error.value = null
    try {
      const data = await clearCache()
      cacheStats.value = normalizeCacheStatsPayload({
        ...createDefaultCacheStats(),
        entries: 0,
        hits: 0
      })
      return data
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '清空缓存失败'
      throw e
    } finally {
      cacheClearing.value = false
    }
  }

  async function loadAIProviders() {
    loading.value = true
    error.value = null
    try {
      const data = await getAIProviders()
      aiProviders.value = Array.isArray(data) ? data : []
      return aiProviders.value
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '加载AI服务商列表失败'
      return []
    } finally {
      loading.value = false
    }
  }

  async function addAIProvider(providerData) {
    error.value = null
    try {
      const data = await createAIProvider(providerData)
      await loadAIProviders()
      return data
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '添加AI服务商失败'
      throw e
    }
  }

  async function editAIProvider(providerId, providerData) {
    error.value = null
    try {
      const data = await updateAIProvider(providerId, providerData)
      await loadAIProviders()
      return data
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '更新AI服务商失败'
      throw e
    }
  }

  async function removeAIProvider(providerId) {
    error.value = null
    try {
      await deleteAIProvider(providerId)
      await loadAIProviders()
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '删除AI服务商失败'
      throw e
    }
  }

  async function loadAIModels(providerId = null, override = null) {
    const payload = {}
    if (providerId !== null && providerId !== undefined) {
      payload.provider_id = providerId
    }
    if (override) {
      payload.override = override
    }
    try {
      const data = await fetchAIModels(payload)
      return data
    } catch (e) {
      console.error('Failed to fetch AI models:', e)
      throw e
    }
  }

  async function testConnection(providerId = null, override = null, model = null) {
    const payload = {}
    if (providerId !== null && providerId !== undefined) {
      payload.provider_id = providerId
    }
    if (override) {
      payload.override = override
    }
    if (model) {
      payload.model = model
    }
    try {
      const data = await testAIConnection(payload)
      return data
    } catch (e) {
      return {
        success: false,
        message: e.response?.data?.detail || e.message || '测试连接失败'
      }
    }
  }

  function reset() {
    settings.value = createDefaultSettings()
    aiProviders.value = []
    cacheStats.value = createDefaultCacheStats()
    loading.value = false
    cacheStatsLoading.value = false
    cacheClearing.value = false
    error.value = null
  }

  return {
    settings,
    aiProviders,
    cacheStats,
    loading,
    cacheStatsLoading,
    cacheClearing,
    error,
    hasSettings,
    loadSettings,
    saveSettings,
    loadCacheStats,
    clearAllCache,
    loadAIProviders,
    addAIProvider,
    editAIProvider,
    removeAIProvider,
    loadAIModels,
    testConnection,
    reset
  }
})
