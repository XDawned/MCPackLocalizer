import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import {
  getModpackDetail,
  getModpackVersions,
  getModpackVersionDetail
} from '@/api/search'

/**
 * 整合包详情状态管理 Store
 * 管理：当前整合包详情、版本列表、选中版本
 */
export const useModpackStore = defineStore('modpack', () => {
  // ========== 当前整合包 ==========
  const platform = ref('')
  const modpackId = ref('')
  const detail = ref(null)
  const loading = ref(false)
  const error = ref(null)

  // ========== 版本列表 ==========
  const versions = ref([])
  const versionsLoading = ref(false)
  const selectedVersion = ref(null)
  const versionDetail = ref(null)
  const versionDetailLoading = ref(false)

  // ========== 计算属性 ==========
  const latestVersion = computed(() => {
    if (versions.value.length === 0) return null
    return versions.value[0]
  })

  const versionCount = computed(() => versions.value.length)

  // ========== 方法 ==========

  /**
   * 加载整合包详情
   * @param {string} plat - 平台
   * @param {string} id - 外部 ID
   */
  async function loadDetail(plat, id) {
    platform.value = plat
    modpackId.value = id
    loading.value = true
    error.value = null

    try {
      const response = await getModpackDetail(plat, id)
      detail.value = response.data || response
    } catch (e) {
      error.value = e.message || '加载整合包详情失败'
      detail.value = null
    } finally {
      loading.value = false
    }
  }

  /**
   * 加载版本列表
   */
  async function loadVersions() {
    if (!platform.value || !modpackId.value) return

    versionsLoading.value = true

    try {
      const response = await getModpackVersions(platform.value, modpackId.value)
      versions.value = response.data || response || []
    } catch (e) {
      console.error('加载版本列表失败:', e)
      versions.value = []
    } finally {
      versionsLoading.value = false
    }
  }

  /**
   * 加载指定版本详情（含 Mod 清单）
   * @param {string} versionId - 版本 ID
   */
  async function loadVersionDetail(versionId) {
    if (!platform.value || !modpackId.value) return

    versionDetailLoading.value = true
    versionDetail.value = null

    try {
      const response = await getModpackVersionDetail(
        platform.value,
        modpackId.value,
        versionId
      )
      versionDetail.value = response.data || response
      selectedVersion.value = versionId
    } catch (e) {
      console.error('加载版本详情失败:', e)
    } finally {
      versionDetailLoading.value = false
    }
  }

  /**
   * 初始化：加载详情 + 版本列表
   */
  async function init(plat, id) {
    await loadDetail(plat, id)
    await loadVersions()
    // 默认加载最新版本详情
    if (versions.value.length > 0) {
      await loadVersionDetail(versions.value[0].id)
    }
  }

  /** 重置状态 */
  function reset() {
    platform.value = ''
    modpackId.value = ''
    detail.value = null
    loading.value = false
    error.value = null
    versions.value = []
    versionsLoading.value = false
    selectedVersion.value = null
    versionDetail.value = null
    versionDetailLoading.value = false
  }

  return {
    platform,
    modpackId,
    detail,
    loading,
    error,
    versions,
    versionsLoading,
    selectedVersion,
    versionDetail,
    versionDetailLoading,
    latestVersion,
    versionCount,
    loadDetail,
    loadVersions,
    loadVersionDetail,
    init,
    reset
  }
})