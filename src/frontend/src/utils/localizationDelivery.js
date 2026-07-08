const AREA_META = {
  mod_lang: {
    label: '模组翻译',
    description: '内容较多，推荐直接使用 i18n 模组',
    color: ''
  },
  ftb_quests: {
    label: 'FTB 任务翻译',
    description: '直接回写 FTB Quests 的 quests/*.snbt 任务文件。',
    color: 'success'
  },
  ftbquests_lang: {
    label: 'FTB Quests 语言树',
    description: '优先写入 ftbquests/lang/zh_cn 等语言树路径。',
    color: 'success'
  },
  better_questing: {
    label: 'Better Questing 任务',
    description: '回写 Better Questing 的任务 JSON 文件。',
    color: 'warning'
  },
  kubejs_json: {
    label: 'KubeJS JSON',
    description: '处理 kubejs 下的 JSON 文件与语言 JSON 文件。',
    color: 'info'
  },
  kubejs_lang: {
    label: 'KubeJS Lang',
    description: '处理 kubejs 下的 .lang 语言文件。',
    color: 'info'
  },
  kubejs_js: {
    label: 'KubeJS JS 文本',
    description: '回写 kubejs 脚本中的可翻译文本。',
    color: 'info'
  },
  unknown: {
    label: '未知区域',
    description: '后端未提供可识别的区域说明。',
    color: 'info'
  }
}

const TARGET_STRATEGY_META = {
  resourcepack: {
    label: '资源包导出',
    description: '输出到资源包 assets 路径。'
  },
  snbt_rewrite: {
    label: 'SNBT 回写',
    description: '直接重写原始 SNBT 文件。'
  },
  ftbquests_lang_file: {
    label: 'FTB 语言树文件',
    description: '写入 FTB Quests 语言树文件。'
  },
  betterquesting_rewrite: {
    label: 'Better Questing 回写',
    description: '直接重写 Better Questing JSON。'
  },
  json_rewrite: {
    label: 'JSON 回写',
    description: '直接重写原 JSON 文件。'
  },
  json_lang_file: {
    label: 'JSON 语言文件',
    description: '生成或更新目标语言 JSON 文件。'
  },
  lang_file: {
    label: 'Lang 语言文件',
    description: '生成或更新目标语言 .lang 文件。'
  },
  js_text_rewrite: {
    label: 'JS 文本回写',
    description: '重写脚本内可翻译文本。'
  },
  unknown: {
    label: '未知策略',
    description: '后端未提供可识别的目标策略。'
  }
}

const DELIVERY_ROOT_LABELS = {
  assets: 'assets（资源包内容）',
  config: 'config（配置 / 任务文件）',
  kubejs: 'kubejs（脚本与语言文件）',
  mods: 'mods（补丁附带模组）',
  resourcepacks: 'resourcepacks（当前阶段仅预留空目录）'
}

export const KUBEJS_AREA_TYPES = ['kubejs_json', 'kubejs_lang', 'kubejs_js']
export const FTBQUESTS_PRIORITY_TYPES = ['ftb_quests', 'ftbquests_lang']

export function normalizePath(path = '') {
  return String(path || '')
    .replace(/\\/g, '/')
    .replace(/^\/+/, '')
}

export function asBooleanSetting(value, fallback = false) {
  if (typeof value === 'boolean') return value
  const normalized = String(value ?? '').trim().toLowerCase()
  if (!normalized) return fallback
  return ['1', 'true', 'yes', 'on'].includes(normalized)
}

export function toBooleanSettingString(value) {
  return value ? 'true' : 'false'
}

export function getAreaMeta(type) {
  return AREA_META[type] || {
    label: type || AREA_META.unknown.label,
    description: AREA_META.unknown.description,
    color: AREA_META.unknown.color
  }
}

export function getTargetStrategyMeta(strategy) {
  return TARGET_STRATEGY_META[strategy] || {
    label: strategy || TARGET_STRATEGY_META.unknown.label,
    description: TARGET_STRATEGY_META.unknown.description
  }
}

export function getTargetStrategyLabel(strategy) {
  return getTargetStrategyMeta(strategy).label
}

export function getItemAreaType(item = {}) {
  return item.area_type || item.apply_metadata?.area_type || 'unknown'
}

export function getItemTargetStrategy(item = {}) {
  return item.target_strategy || item.apply_metadata?.target_strategy || 'unknown'
}

export function getItemTargetPath(item = {}) {
  return normalizePath(
    item.target_path
    || item.apply_metadata?.target_path
    || item.apply_metadata?.target_relative_path
    || ''
  )
}

export function getItemSourcePath(item = {}) {
  return normalizePath(
    item.apply_metadata?.source_relative_path
    || item.source_path
    || ''
  )
}

export function getAreaSelectionSummary(selectableAreas = [], selectedAreas = []) {
  const selectedSet = new Set(selectedAreas)
  const totalFiles = selectableAreas.reduce((sum, area) => sum + Number(area?.count || 0), 0)
  const selectedFiles = selectableAreas.reduce((sum, area) => {
    if (!selectedSet.has(area?.type)) return sum
    return sum + Number(area?.count || 0)
  }, 0)

  return {
    totalAreas: selectableAreas.length,
    selectedAreas: selectableAreas.filter(area => selectedSet.has(area?.type)).length,
    totalFiles,
    selectedFiles
  }
}

function estimateTextBytes(value = '') {
  return new TextEncoder().encode(String(value || '')).length
}

function isLikelyModifiedTarget(item = {}) {
  const strategy = getItemTargetStrategy(item)
  const sourcePath = getItemSourcePath(item)
  const targetPath = getItemTargetPath(item)

  if (!targetPath) return false
  if (sourcePath && sourcePath === targetPath) return true

  return [
    'snbt_rewrite',
    'betterquesting_rewrite',
    'json_rewrite',
    'js_text_rewrite'
  ].includes(strategy)
}

export function buildDeliveryPreview(items = []) {
  const grouped = new Map()

  items.forEach(item => {
    if (!item) return
    const targetPath = getItemTargetPath(item)
    if (!targetPath) return

    const current = grouped.get(targetPath) || {
      path: targetPath,
      original_size: 0,
      new_size: 0,
      size: 0,
      itemCount: 0,
      area_type: getItemAreaType(item),
      target_strategy: getItemTargetStrategy(item),
      modified: false
    }

    current.itemCount += 1
    current.modified = current.modified || isLikelyModifiedTarget(item)
    current.original_size += estimateTextBytes(item.original_text || '')
    current.new_size += estimateTextBytes(item.translated_text || item.original_text || '')
    current.size = current.new_size
    grouped.set(targetPath, current)
  })

  const modifiedFiles = []
  const addedFiles = []
  const pathMeta = {}

  Array.from(grouped.values())
    .sort((left, right) => left.path.localeCompare(right.path, 'zh-CN'))
    .forEach(group => {
      const payload = {
        path: group.path,
        original_size: group.original_size,
        new_size: group.new_size,
        size: group.size,
        itemCount: group.itemCount,
        area_type: group.area_type,
        target_strategy: group.target_strategy
      }

      pathMeta[group.path] = payload

      if (group.modified) {
        modifiedFiles.push(payload)
      } else {
        addedFiles.push(payload)
      }
    })

  return {
    modifiedFiles,
    addedFiles,
    pathMeta,
    itemCount: items.length
  }
}

export function summarizeTaskTargets(items = []) {
  const areaMap = new Map()
  const strategyMap = new Map()
  const rootMap = new Map()
  const sampleTargets = []
  const seenTargets = new Set()

  items.forEach(item => {
    if (!item) return

    const areaType = getItemAreaType(item)
    const targetStrategy = getItemTargetStrategy(item)
    const targetPath = getItemTargetPath(item)
    const targetRoot = targetPath.split('/')[0] || 'unknown'

    areaMap.set(areaType, (areaMap.get(areaType) || 0) + 1)
    strategyMap.set(targetStrategy, (strategyMap.get(targetStrategy) || 0) + 1)
    if (targetPath) {
      rootMap.set(targetRoot, (rootMap.get(targetRoot) || 0) + 1)
      if (!seenTargets.has(targetPath) && sampleTargets.length < 8) {
        sampleTargets.push({
          path: targetPath,
          areaType,
          targetStrategy,
          sourceFile: item.source_file || ''
        })
        seenTargets.add(targetPath)
      }
    }
  })

  return {
    areaCounts: Array.from(areaMap.entries()).map(([type, count]) => ({
      type,
      count,
      ...getAreaMeta(type)
    })),
    strategyCounts: Array.from(strategyMap.entries()).map(([strategy, count]) => ({
      strategy,
      count,
      ...getTargetStrategyMeta(strategy)
    })),
    targetRoots: Array.from(rootMap.entries()).map(([root, count]) => ({
      root,
      count,
      label: DELIVERY_ROOT_LABELS[root] || root
    })),
    sampleTargets
  }
}

export function summarizePatchStructure(result = {}) {
  const writtenFiles = Array.isArray(result.written_files) ? result.written_files : []
  const placeholderDirectories = Array.isArray(result.placeholder_directories) ? result.placeholder_directories : []
  const roots = ['config', 'kubejs', 'mods', 'resourcepacks']

  return roots.map(root => ({
    root,
    label: DELIVERY_ROOT_LABELS[root] || root,
    writtenCount: writtenFiles.filter(path => normalizePath(path).startsWith(`${root}/`) || normalizePath(path) === root).length,
    reserved: placeholderDirectories.includes(root)
  }))
}

export function getI18nModStatusMeta(mod = {}) {
  const status = String(mod?.status || '')
  const mapping = {
    skipped_disabled: { type: 'info', label: '未附带' },
    skipped_missing_context: { type: 'warning', label: '缺少版本上下文' },
    reused_local: { type: 'success', label: '复用实例现有文件' },
    reused_cache: { type: 'success', label: '复用本地缓存' },
    downloaded_modrinth: { type: 'success', label: '已从 Modrinth 下载' },
    downloaded_curseforge: { type: 'success', label: '已从 CurseForge 下载' },
    unavailable: { type: 'warning', label: '未找到匹配文件' }
  }

  return mapping[status] || { type: 'info', label: status || '未处理' }
}

export function getDeliveryRootLabel(root) {
  return DELIVERY_ROOT_LABELS[root] || root
}

export function formatAreaCountText(area = {}) {
  const count = Number(area?.count || 0)
  return `${count} 文件`
}
