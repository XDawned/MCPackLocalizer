import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import {
  discoverPackFolder,
  scanPackFolder,
  getScanStatus,
  getScanAreas,
  extractContent,
} from '@/api/packScan'

const FLOW_STAGE = {
  IDLE: 'idle',
  DISCOVERING: 'discovering',
  WAITING_GAME_SELECT: 'waiting_game_select',
  SCANNING: 'scanning',
  COMPLETED: 'completed',
  FAILED: 'failed',
}

const DEFAULT_EXCLUDED_AREA_TYPES = ['mod_lang']

function getDefaultSelectedAreaTypes(areas) {
  return areas
    .filter(area => !DEFAULT_EXCLUDED_AREA_TYPES.includes(area.type))
    .map(area => area.type)
}

function normalizeErrorMessage(error, fallbackMessage) {
  const detail = error?.response?.data?.detail
  const message = error?.message
  const rawMessage = typeof detail === 'string' ? detail : message

  if (!rawMessage) {
    return fallbackMessage
  }

  if (rawMessage.includes('game_name')) {
    return '检测到多个游戏实例，请先选择要扫描的实例后再继续。'
  }

  if (rawMessage.includes('work root') || rawMessage.includes('mods/config')) {
    return '未找到可用的工作目录，请确认实例目录中包含 mods 或 config 后重试。'
  }

  if (rawMessage.includes('local_path')) {
    return '所选目录无效，请确认路径存在且可访问。'
  }

  return rawMessage
}

function isVersionsCandidatePreferred(candidate) {
  return candidate?.has_version_work_root
}

export const useLocalPackStore = defineStore('localPack', () => {
  const folderPath = ref('')
  const flowStage = ref(FLOW_STAGE.IDLE)
  const scanResult = ref(null)
  const discoverResult = ref(null)
  const versionCandidates = ref([])
  const selectedGameName = ref('')
  const scanLoading = ref(false)
  const areas = ref([])
  const selectableAreas = ref([])
  const selectedAreas = ref([])
  const extractResult = ref(null)
  const error = ref(null)
  const minecraftRoot = ref('')
  const workRoot = ref('')
  const workRootSource = ref('')
  const packType = ref('')
  const versionResolutionSource = ref('')
  const recommendedAction = ref('')

  const hasResult = computed(() => scanResult.value !== null)
  const translatableAreas = computed(() => areas.value.filter(a => a.count > 0))
  const selectedCandidate = computed(() =>
    versionCandidates.value.find(candidate => candidate.game_name === selectedGameName.value) || null
  )
  const requiresGameSelection = computed(() =>
    flowStage.value === FLOW_STAGE.WAITING_GAME_SELECT && versionCandidates.value.length > 1
  )
  const canStartLocalization = computed(() =>
    flowStage.value === FLOW_STAGE.COMPLETED && hasResult.value
  )
  const currentWorkRootHint = computed(() => {
    if (selectedCandidate.value?.has_version_work_root) {
      return selectedCandidate.value.version_work_root || selectedCandidate.value.version_root || ''
    }

    if (selectedCandidate.value?.fallback_minecraft_root_usable) {
      return discoverResult.value?.minecraft_root || ''
    }

    return workRoot.value || ''
  })

  function applyScanData(data) {
    scanResult.value = data
    areas.value = data.areas || []
    selectableAreas.value = (data.areas || []).filter(a => a.count > 0)
    selectedAreas.value = getDefaultSelectedAreaTypes(selectableAreas.value)
    minecraftRoot.value = data.minecraft_root || discoverResult.value?.minecraft_root || ''
    workRoot.value = data.work_root || data.real_path || ''
    workRootSource.value = data.work_root_source || ''
    packType.value = data.pack_type || discoverResult.value?.pack_type || ''
    versionResolutionSource.value = data.version_resolution_source || ''
  }

  function clearScanState() {
    scanResult.value = null
    areas.value = []
    selectableAreas.value = []
    selectedAreas.value = []
    extractResult.value = null
    minecraftRoot.value = ''
    workRoot.value = ''
    workRootSource.value = ''
    versionResolutionSource.value = ''
  }

  function prepareNewFlow(path) {
    folderPath.value = path
    error.value = null
    flowStage.value = FLOW_STAGE.DISCOVERING
    discoverResult.value = null
    versionCandidates.value = []
    selectedGameName.value = ''
    recommendedAction.value = ''
    packType.value = ''
    clearScanState()
  }

  async function runScan(path, gameName = null) {
    flowStage.value = FLOW_STAGE.SCANNING
    scanLoading.value = true
    error.value = null

    try {
      const res = await scanPackFolder(path, gameName)
      const data = res.data || res
      applyScanData(data)
      flowStage.value = FLOW_STAGE.COMPLETED
      return data
    } catch (e) {
      flowStage.value = FLOW_STAGE.FAILED
      error.value = normalizeErrorMessage(e, '扫描失败')
      return null
    } finally {
      scanLoading.value = false
    }
  }

  async function scanFolder(path) {
    prepareNewFlow(path)
    scanLoading.value = true

    try {
      const res = await discoverPackFolder(path)
      const data = res.data || res
      discoverResult.value = data
      versionCandidates.value = data.candidates || []
      recommendedAction.value = data.recommended_action || ''
      packType.value = data.pack_type || ''
      minecraftRoot.value = data.minecraft_root || ''

      if (versionCandidates.value.length > 1) {
        flowStage.value = FLOW_STAGE.WAITING_GAME_SELECT
        return { requiresSelection: true, discoverResult: data }
      }

      if (versionCandidates.value.length === 1) {
        selectedGameName.value = versionCandidates.value[0].game_name || ''
      }

      return await runScan(path, selectedGameName.value || null)
    } catch (e) {
      flowStage.value = FLOW_STAGE.FAILED
      error.value = normalizeErrorMessage(e, '扫描失败')
      return null
    } finally {
      if (flowStage.value !== FLOW_STAGE.SCANNING) {
        scanLoading.value = false
      }
    }
  }

  async function continueScanWithSelectedGame() {
    if (!folderPath.value) {
      error.value = '请先选择整合包目录。'
      return null
    }

    if (!selectedGameName.value) {
      error.value = '请先选择要扫描的游戏实例。'
      flowStage.value = FLOW_STAGE.WAITING_GAME_SELECT
      return null
    }

    return await runScan(folderPath.value, selectedGameName.value)
  }

  async function loadAreas(scanId) {
    try {
      const res = await getScanAreas(scanId)
      const data = res.data || res
      areas.value = Array.isArray(data) ? data : data.areas || []
      selectableAreas.value = areas.value.filter(a => a.count > 0)
      if (!selectedAreas.value.length) {
        selectedAreas.value = getDefaultSelectedAreaTypes(selectableAreas.value)
      }
      return areas.value
    } catch (e) {
      error.value = normalizeErrorMessage(e, '获取区域信息失败')
      return []
    }
  }

  async function extract(scanId) {
    error.value = null
    extractResult.value = null
    try {
      const res = await extractContent(scanId, selectedAreas.value)
      const data = res.data || res
      extractResult.value = data
      return data
    } catch (e) {
      error.value = normalizeErrorMessage(e, '提取内容失败')
      return null
    }
  }

  function setSelectedGameName(gameName) {
    selectedGameName.value = gameName || ''
    if (selectedGameName.value && flowStage.value === FLOW_STAGE.FAILED && versionCandidates.value.length > 1) {
      flowStage.value = FLOW_STAGE.WAITING_GAME_SELECT
    }
  }

  function toggleArea(type) {
    const idx = selectedAreas.value.indexOf(type)
    if (idx >= 0) {
      selectedAreas.value.splice(idx, 1)
    } else {
      selectedAreas.value.push(type)
    }
  }

  function reset() {
    folderPath.value = ''
    flowStage.value = FLOW_STAGE.IDLE
    discoverResult.value = null
    versionCandidates.value = []
    selectedGameName.value = ''
    scanLoading.value = false
    recommendedAction.value = ''
    packType.value = ''
    clearScanState()
    error.value = null
  }

  return {
    FLOW_STAGE,
    folderPath,
    flowStage,
    scanResult,
    discoverResult,
    versionCandidates,
    selectedGameName,
    scanLoading,
    areas,
    selectableAreas,
    selectedAreas,
    extractResult,
    error,
    minecraftRoot,
    workRoot,
    workRootSource,
    packType,
    versionResolutionSource,
    recommendedAction,
    hasResult,
    translatableAreas,
    selectedCandidate,
    requiresGameSelection,
    canStartLocalization,
    currentWorkRootHint,
    scanFolder,
    continueScanWithSelectedGame,
    loadAreas,
    extract,
    setSelectedGameName,
    toggleArea,
    reset,
    isVersionsCandidatePreferred,
  }
})
