import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import {
  applyTranslation as applyTranslationApi,
  restoreBackup as restoreBackupApi,
  getBackups as getBackupsApi,
  deleteBackup as deleteBackupApi,
  generatePatchPackage as generatePatchPackageApi
} from '@/api/apply'
import { generateResourcePack as generateResourcePackApi } from '@/api/resourcepack'

function normalizeBackups(payload) {
  if (Array.isArray(payload)) return payload
  return payload?.backups || payload?.results || payload?.items || []
}

function normalizeErrorMessage(error, fallback) {
  return error?.response?.data?.detail || error?.message || fallback
}

export const useApplyStore = defineStore('apply', () => {
  const backups = ref([])
  const loading = ref(false)
  const applying = ref(false)
  const restoring = ref(false)
  const restoringBackupId = ref(null)
  const deletingBackupIds = ref([])
  const generating = ref(false)
  const generationKind = ref('')
  const resourcePack = ref(null)
  const patchPackage = ref(null)
  const error = ref(null)
  const currentModpackVersionId = ref(null)
  const lastAppliedBackup = ref(null)

  const hasBackups = computed(() => backups.value.length > 0)
  const activeBackup = computed(() => backups.value.find(item => item.status === 'active') || null)
  const hasResourcePack = computed(() => Boolean(resourcePack.value?.download_url))
  const hasPatchPackage = computed(() => Boolean(patchPackage.value?.patch_path))
  const downloadUrl = computed(() => resourcePack.value?.download_url || '')
  const isGeneratingPatch = computed(() => generating.value && generationKind.value === 'patch')
  const isGeneratingResourcePack = computed(() => generating.value && generationKind.value === 'resourcepack')

  function isDeletingBackup(backupId) {
    return deletingBackupIds.value.includes(backupId)
  }

  function isRestoringBackup(backupId) {
    return restoringBackupId.value === backupId
  }

  async function loadBackups(modpackVersionId = currentModpackVersionId.value) {
    loading.value = true
    error.value = null
    currentModpackVersionId.value = modpackVersionId ?? null

    try {
      const params = {}
      if (modpackVersionId !== null && modpackVersionId !== undefined && modpackVersionId !== '') {
        params.modpack_version_id = modpackVersionId
      }

      const data = await getBackupsApi(Object.keys(params).length > 0 ? params : undefined)
      backups.value = normalizeBackups(data)
      return backups.value
    } catch (e) {
      error.value = normalizeErrorMessage(e, '加载备份列表失败')
      backups.value = []
      return []
    } finally {
      loading.value = false
    }
  }

  async function applyTranslation(taskId) {
    applying.value = true
    error.value = null

    try {
      const data = await applyTranslationApi(taskId)
      lastAppliedBackup.value = data || null

      if (data?.modpack_version_id !== null && data?.modpack_version_id !== undefined) {
        currentModpackVersionId.value = data.modpack_version_id
      }

      await loadBackups(currentModpackVersionId.value)
      return data
    } catch (e) {
      error.value = normalizeErrorMessage(e, '应用翻译失败')
      throw e
    } finally {
      applying.value = false
    }
  }

  async function restoreBackup(backupId) {
    restoring.value = true
    restoringBackupId.value = backupId
    error.value = null

    try {
      const data = await restoreBackupApi(backupId)
      await loadBackups(currentModpackVersionId.value)
      return data
    } catch (e) {
      error.value = normalizeErrorMessage(e, '还原翻译失败')
      throw e
    } finally {
      restoring.value = false
      restoringBackupId.value = null
    }
  }

  async function removeBackup(backupId) {
    error.value = null
    deletingBackupIds.value = [...deletingBackupIds.value, backupId]

    try {
      await deleteBackupApi(backupId)
      backups.value = backups.value.filter(backup => backup.id !== backupId)
      if (lastAppliedBackup.value?.id === backupId) {
        lastAppliedBackup.value = null
      }
    } catch (e) {
      error.value = normalizeErrorMessage(e, '删除备份失败')
      throw e
    } finally {
      deletingBackupIds.value = deletingBackupIds.value.filter(id => id !== backupId)
    }
  }

  async function generateResourcePack(taskId, config = {}) {
    generating.value = true
    generationKind.value = 'resourcepack'
    error.value = null

    try {
      const data = await generateResourcePackApi(taskId, config)
      resourcePack.value = data || null
      return data
    } catch (e) {
      error.value = normalizeErrorMessage(e, '生成资源包失败')
      throw e
    } finally {
      generating.value = false
      generationKind.value = ''
    }
  }

  async function generatePatchPackage(taskId, config = {}) {
    generating.value = true
    generationKind.value = 'patch'
    error.value = null

    try {
      const data = await generatePatchPackageApi(taskId, config)
      patchPackage.value = data || null
      return data
    } catch (e) {
      error.value = normalizeErrorMessage(e, '生成补丁目录失败')
      throw e
    } finally {
      generating.value = false
      generationKind.value = ''
    }
  }

  function setResourcePack(data) {
    resourcePack.value = data || null
  }

  function clearResourcePack() {
    resourcePack.value = null
  }

  function setPatchPackage(data) {
    patchPackage.value = data || null
  }

  function clearPatchPackage() {
    patchPackage.value = null
  }

  function reset() {
    backups.value = []
    loading.value = false
    applying.value = false
    restoring.value = false
    restoringBackupId.value = null
    deletingBackupIds.value = []
    generating.value = false
    generationKind.value = ''
    resourcePack.value = null
    patchPackage.value = null
    error.value = null
    currentModpackVersionId.value = null
    lastAppliedBackup.value = null
  }

  return {
    backups,
    loading,
    applying,
    restoring,
    restoringBackupId,
    deletingBackupIds,
    generating,
    generationKind,
    resourcePack,
    patchPackage,
    error,
    currentModpackVersionId,
    lastAppliedBackup,
    hasBackups,
    activeBackup,
    hasResourcePack,
    hasPatchPackage,
    downloadUrl,
    isGeneratingPatch,
    isGeneratingResourcePack,
    isDeletingBackup,
    isRestoringBackup,
    loadBackups,
    applyTranslation,
    restoreBackup,
    deleteBackup: removeBackup,
    generateResourcePack,
    generatePatchPackage,
    setResourcePack,
    clearResourcePack,
    setPatchPackage,
    clearPatchPackage,
    reset
  }
})
