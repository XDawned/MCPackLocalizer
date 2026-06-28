<script setup>
import { computed, ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElButton, ElInput, ElAlert, ElMessage, ElTag } from 'element-plus'
import { useLocalPackStore } from '@/stores/localPack'
import { useWorkflowStore } from '@/stores/workflow'
import LocalPackScanner from '@/components/common/LocalPackScanner.vue'
import TranslatableAreas from '@/components/common/TranslatableAreas.vue'

const router = useRouter()
const localPackStore = useLocalPackStore()
const workflowStore = useWorkflowStore()

const folderPathInput = ref('')
const submitLoading = ref(false)
const isDragOver = ref(false)
const dragIndicator = reactive({ x: 0, y: 0 })

const electronApi = window.electronAPI
const isElectronWithDialog = typeof electronApi?.openDirectoryDialog === 'function'

const stageLabelMap = {
  idle: '等待选择目录',
  discovering: '正在识别目录结构',
  waiting_game_select: '等待选择实例',
  scanning: '正在扫描内容',
  completed: '扫描完成',
  failed: '扫描失败',
}

const currentStageLabel = computed(() => stageLabelMap[localPackStore.flowStage] || '处理中')
const canShowAreas = computed(() => localPackStore.hasResult)
const canStartLocalization = computed(() =>
  localPackStore.canStartLocalization && localPackStore.selectedAreas.length > 0
)
const summaryMetrics = computed(() => {
  const result = localPackStore.scanResult || {}
  const areas = Array.isArray(result.areas) ? result.areas : []
  const totalFiles = areas.reduce((sum, area) => sum + (Number(area.count) || 0), 0)
  const issueCount = (Array.isArray(result.warnings) ? result.warnings.length : 0)
    + (Array.isArray(result.errors) ? result.errors.length : 0)

  return [
    {
      label: '识别类型',
      value: result.pack_type || localPackStore.packType || '未识别',
      tone: result.pack_type || localPackStore.packType ? 'default' : 'empty',
    },
    {
      label: 'MC 版本',
      value: result.mc_version || '未提供版本信息',
      tone: result.mc_version ? 'default' : 'empty',
    },
    {
      label: '版本关键字',
      value: localPackStore.versionResolutionSource || '未检索到MC版本',
      tone: localPackStore.versionResolutionSource ? 'default' : 'empty',
    },
    {
      label: 'Mod 数量',
      value: typeof result.mod_count === 'number' ? `${result.mod_count}` : '未统计',
      tone: typeof result.mod_count === 'number' ? 'default' : 'empty',
    },
    {
      label: '扫描文件数',
      value: totalFiles > 0 ? `${totalFiles}` : '暂无可翻译文件',
      tone: totalFiles > 0 ? 'default' : 'empty',
    },
    {
      label: '异常摘要',
      value: issueCount > 0 ? `异常 ${issueCount}` : '无异常',
      tone: issueCount > 0 ? 'warning' : 'success',
    },
  ]
})

function getCandidateStrategyText(candidate) {
  if (localPackStore.isVersionsCandidatePreferred(candidate)) {
    return '优先目录'
  }
  if (candidate?.fallback_minecraft_root_usable) {
    return '回退根目录'
  }
  return '不可直扫'
}

function getWorkRootSourceText(source) {
  const textMap = {
    version_work_root: '版本目录',
    minecraft_root: '.minecraft 根目录',
    direct_input: '输入目录',
    direct_scan: '输入目录',
    selected_candidate: '手动实例',
    auto_selected_candidate: '自动实例',
  }
  return textMap[source] || source || '未知'
}

async function handleScan() {
  const path = folderPathInput.value.trim()
  if (!path) return

  submitLoading.value = true
  try {
    const result = await localPackStore.scanFolder(path)

    if (result) {
      await electronApi?.closeDirectoryDialog?.()
    }
  } finally {
    submitLoading.value = false
  }
}

async function handleContinueWithSelection() {
  submitLoading.value = true
  try {
    const result = await localPackStore.continueScanWithSelectedGame()
    if (result) {
      await electronApi?.closeDirectoryDialog?.()
    }
  } finally {
    submitLoading.value = false
  }
}

async function handleSelectFolder() {
  if (isElectronWithDialog) {
    try {
      const selectedPath = await electronApi.openDirectoryDialog()

      if (selectedPath) {
        folderPathInput.value = selectedPath
        await handleScan()
      }
    } catch (error) {
      ElMessage.warning('选择目录失败，请手动输入路径')
    }
  } else {
    ElMessage.warning('网页模式下无法获取本地路径，请手动输入')
  }
}

function handleDragOver(e) {
  e.preventDefault()
  if (!e.dataTransfer) return
  e.dataTransfer.dropEffect = 'copy'
  isDragOver.value = true
  dragIndicator.x = e.clientX
  dragIndicator.y = e.clientY
}

function handleDragLeave(e) {
  if (e.currentTarget.contains(e.relatedTarget)) return
  isDragOver.value = false
}

async function handleDrop(e) {
  e.preventDefault()
  isDragOver.value = false

  const droppedPath = extractPathFromDataTransfer(e.dataTransfer)
  console.info('[LocalImportView] handleDrop', {
    droppedPath,
    fileCount: e.dataTransfer?.files?.length || 0,
    itemCount: e.dataTransfer?.items?.length || 0,
  })

  if (droppedPath) {
    folderPathInput.value = droppedPath
    await handleScan()
  } else {
    ElMessage.warning('未能获取拖入目录路径，请尝试直接输入')
  }
}

function extractPathFromDataTransfer(dataTransfer) {
  if (!dataTransfer) return null

  const items = Array.from(dataTransfer.items || [])
  for (const item of items) {
    const file = item.getAsFile?.()
    const entry = item.webkitGetAsEntry?.()
    const path = extractPathFromFileLike(file) || extractPathFromEntry(entry)
    if (path) {
      return path
    }
  }

  const files = Array.from(dataTransfer.files || [])
  for (const file of files) {
    const path = extractPathFromFileLike(file)
    if (path) {
      return path
    }
  }

  return null
}

function extractPathFromFileLike(file) {
  if (file?.path && file.path.length > 0) {
    return file.path
  }

  if (typeof file?.name === 'string' && file.name.length > 0) {
    const maybePath = file.name
    if (maybePath.includes(':\\') || maybePath.startsWith('/') || maybePath.startsWith('\\\\')) {
      return maybePath
    }
  }

  return null
}

function extractPathFromEntry(entry) {
  if (!entry) return null

  if (typeof entry.fullPath === 'string' && entry.fullPath.length > 0 && !entry.fullPath.startsWith('/')) {
    return entry.fullPath
  }

  return null
}

function handleStartLocalization() {
  if (!canStartLocalization.value) return

  const resolvedLocalPath =
    localPackStore.workRoot ||
    localPackStore.currentWorkRootHint ||
    localPackStore.folderPath
  const scanId = localPackStore.scanResult?.scan_id
  workflowStore.startWorkflow('0', resolvedLocalPath, scanId)
  router.push(
    workflowStore.getStepLocation(2, {
      localPath: resolvedLocalPath,
      scanId,
      modpackVersionId: '0'
    })
  )
}
</script>

<template>
  <div class="local-import-view">
    <ElAlert
      v-if="localPackStore.error"
      :title="localPackStore.error"
      type="error"
      closable
      class="view-alert"
      @close="localPackStore.error = null"
    />
    <section
      class="section-card section-card--action"
      :class="{ 'section-card--dragover': isDragOver }"
      @dragover="handleDragOver"
      @dragleave="handleDragLeave"
      @drop="handleDrop"
    >
      <div class="section-card__header section-card__header--aligned">
        <div>
          <p class="section-card__eyebrow">Import</p>
          <h2 class="section-card__title">选择游戏目录</h2>
        </div>
        <p class="section-card__desc">识别游戏结构</p>
      </div>

      <div class="scan-action-layout">
        <div class="command-surface">
          <div class="command-surface__header">
            <div>
              <div class="command-surface__title">目录源</div>
              <p class="command-surface__desc">指定目录后执行扫描。</p>
            </div>
            <div class="command-surface__badge">{{ submitLoading ? '处理中' : '就绪' }}</div>
          </div>

          <div class="folder-input-row">
            <ElInput
                v-model="folderPathInput"
                placeholder="例如: D:/MC/instances/ATM9/"
                class="folder-input"
                size="large"
                :disabled="submitLoading"
                @keyup.enter="handleScan"
            >
              <template #prepend>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                </svg>
              </template>
            </ElInput>
            <ElButton
                size="large"
                class="btn-browse"
                @click="handleSelectFolder"
                :disabled="submitLoading"
            >
              浏览
            </ElButton>
            <ElButton
                type="primary"
                size="large"
                class="btn-scan"
                :loading="submitLoading && !localPackStore.requiresGameSelection"
                :disabled="!folderPathInput.trim() || submitLoading"
                @click="handleScan"
            >
              扫描
            </ElButton>
          </div>

          <div class="folder-info-row">
            <div class="command-status-card">
              <span class="command-status-card__label">当前目录</span>
              <span class="command-status-card__value command-status-card__value--path" :class="{ 'command-status-card__value--empty': !folderPathInput.trim() }">
                  {{ folderPathInput.trim() || '等待目录' }}
                </span>
            </div>
          </div>

          <div class="drop-zone-note" :class="{ 'drop-zone-note--active': isDragOver }">
            <div class="drop-zone-note__icon">
              <svg class="drop-hint-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </div>
            <div>
              <div class="drop-zone-note__title">拖放目录</div>
              <p class="drop-zone-note__text">将<code>.minecraft</code>目录拖拽到此处进行识别</p>
            </div>
          </div>
        </div>

        <div class="mini-note-card scan-side-notes">
          <div class="mini-note-card__label">当前状态</div>
          <div class="mini-note-card__value">{{ currentStageLabel }}</div>
          <p class="mini-note-card__text">结果区同步更新</p>
        </div>
      </div>
    </section>

    <section class="section-card section-card--results">
      <div class="section-card__header section-card__header--aligned">
        <div>
          <p class="section-card__eyebrow">Results</p>
          <h2 class="section-card__title">扫描结果</h2>
        </div>
        <p class="section-card__desc">检查游戏版本信息</p>
      </div>

      <div class="results-stack">
        <div v-if="!canShowAreas" class="results-surface results-surface--scanner">
          <div class="results-surface__header">
            <div>
              <div class="results-surface__title">扫描详情</div>
              <p class="results-surface__desc">当前扫描信息。</p>
            </div>
          </div>
          <LocalPackScanner :compact="false" @next="" />
        </div>

        <div class="scan-summary-panel">
          <div class="summary-highlight-card">
            <div class="summary-highlight-card__label">整合包名称</div>
            <div class="summary-highlight-card__value" :class="{ 'summary-highlight-card__value--empty': !localPackStore.scanResult?.name }">
              {{ localPackStore.scanResult?.name || '未识别名称' }}
            </div>
            <p class="summary-highlight-card__text">{{ localPackStore.scanResult?.game_name || '未指定实例 / 自动识别实例' }}</p>
          </div>

          <div class="summary-metrics-grid">
            <article
              v-for="metric in summaryMetrics"
              :key="metric.label"
              class="metric-card"
              :class="`metric-card--${metric.tone}`"
            >
              <div class="metric-card__label">{{ metric.label }}</div>
              <div class="metric-card__value">{{ metric.value }}</div>
            </article>
          </div>
        </div>

        <div class="scan-summary scan-summary--detail">
          <div class="summary-item">
            <span class="summary-label">游戏实例</span>
            <span class="summary-value" :class="{ 'summary-value--empty': !localPackStore.scanResult?.game_name }">{{ localPackStore.scanResult?.game_name || '未指定 / 自动识别' }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">工作根目录</span>
            <span class="summary-value summary-value--path" :class="{ 'summary-value--empty': !(localPackStore.workRoot || localPackStore.scanResult?.real_path) }">
              {{ localPackStore.workRoot || localPackStore.scanResult?.real_path || '未识别工作根目录' }}
            </span>
          </div>
          <div class="summary-item">
            <span class="summary-label">工作根来源</span>
            <span class="summary-value" :class="{ 'summary-value--empty': !localPackStore.workRootSource }">{{ getWorkRootSourceText(localPackStore.workRootSource) }}</span>
          </div>
        </div>

        <div class="translation-section-card">
          <div class="translation-section-card__header">
            <div>
              <h3 class="translation-section-card__title">翻译范围</h3>
              <p class="translation-section-card__desc">选择需要进入 AI 流程的内容。</p>
            </div>
          </div>
          <TranslatableAreas />
        </div>
      </div>
    </section>

    <div class="action-bar" v-if="canShowAreas">
      <div class="action-bar__note">确认后进入下一步。</div>
      <ElButton
        type="primary"
        size="large"
        class="btn-start"
        @click="handleStartLocalization"
        :disabled="!canStartLocalization"
      >
        开始本地化
      </ElButton>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.local-import-view {
  max-width: 1120px;
  margin: 0 auto;
  padding: var(--notion-spacing-xxl) var(--notion-spacing-xl) 72px;
}

.section-card__eyebrow,
.mini-note-card__label,
.metric-card__label,
.summary-highlight-card__label,
.command-status-card__label {
  font-size: var(--notion-font-size-micro-uppercase);
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--notion-stone);
}

.mini-note-card,
.translation-section-card,
.command-surface,
.results-surface {
  background: var(--notion-canvas);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
}


.mini-note-card__value,
.summary-highlight-card__value {
  margin-top: var(--notion-spacing-xs);
  font-size: var(--notion-font-size-h5);
  line-height: var(--notion-line-height-h5);
  font-weight: 620;
  letter-spacing: -0.01em;
  color: var(--notion-ink);
}

.mini-note-card--status {
  padding: var(--notion-spacing-sm), var(--notion-spacing-xs)!important;
}

.command-status-card__value--path {
  word-break: break-all;
  font-size: var(--notion-font-size-body-sm);
  line-height: var(--notion-line-height-body-sm);
}

.mini-note-card__text,
.section-card__desc,
.summary-highlight-card__text,
.translation-section-card__desc,
.command-surface__desc,
.results-surface__desc {
  margin-top: 6px;
  font-size: var(--notion-font-size-body-sm);
  line-height: 1.45;
  color: var(--notion-steel);
}

.view-alert {
  margin-bottom: var(--notion-spacing-md);
}

:deep(.view-alert.el-alert) {
  border-radius: var(--notion-rounded-lg);
  border: 1px solid rgba(207, 60, 60, 0.16);
}

.section-card {
  margin-bottom: var(--notion-spacing-lg);
  padding: var(--notion-spacing-xl);
  background: var(--notion-canvas);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.03);
}

.section-card--muted {
  background: linear-gradient(180deg, var(--notion-surface-soft) 0%, rgba(255, 255, 255, 0.65) 100%);
}

.section-card--results {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.92) 0%, rgba(246, 248, 252, 0.92) 100%);
}

.section-card--action {
  transition: border-color var(--notion-transition-fast), background var(--notion-transition-fast), box-shadow var(--notion-transition-fast), transform var(--notion-transition-fast);
}

.section-card--dragover {
  border-color: var(--notion-primary);
  background: linear-gradient(180deg, rgba(86, 69, 212, 0.06) 0%, rgba(86, 69, 212, 0.02) 100%);
  box-shadow: 0 0 0 3px rgba(86, 69, 212, 0.08);
  transform: translateY(-1px);
}

.section-card__header {
  display: flex;
  flex-direction: column;
  gap: var(--notion-spacing-xs);
  margin-bottom: var(--notion-spacing-lg);
}

.section-card__header--aligned {
  flex-direction: row;
  align-items: flex-start;
  justify-content: space-between;
}

.section-card__title {
  margin-top: 6px;
  font-size: var(--notion-font-size-h5);
  font-weight: 620;
  letter-spacing: -0.01em;
  color: var(--notion-ink);
}

.scan-action-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(250px, 0.9fr);
  gap: var(--notion-spacing-lg);
}

.scan-side-notes {
  padding: var(--notion-spacing-xl);
}

.command-surface,
.results-surface,
.translation-section-card {
  padding: var(--notion-spacing-lg);
}

.command-surface__header,
.results-surface__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--notion-spacing-sm);
  margin-bottom: var(--notion-spacing-md);
}

.command-surface__title,
.results-surface__title,
.translation-section-card__title {
  font-size: var(--notion-font-size-body);
  font-weight: 620;
  letter-spacing: -0.01em;
  color: var(--notion-ink);
}

.command-surface__badge {
  flex-shrink: 0;
  padding: 6px 10px;
  border-radius: var(--notion-rounded-full);
  border: 1px solid var(--notion-hairline);
  background: rgba(255, 255, 255, 0.72);
  font-size: var(--notion-font-size-micro);
  color: var(--notion-stone);
  letter-spacing: 0.04em;
}

.folder-input-row {
  display: flex;
  gap: var(--notion-spacing-sm);
  align-items: stretch;
}

.folder-info-row {
  margin-top: var(--notion-spacing-md);
}

.folder-input {
  flex: 1;
}

:deep(.folder-input .el-input__wrapper),
:deep(.folder-input .el-input-group__prepend),
:deep(.btn-browse.el-button),
:deep(.btn-scan.el-button),
:deep(.btn-start.el-button) {
  min-height: 44px;
  border-radius: var(--notion-rounded-md);
}

:deep(.folder-input .el-input__wrapper) {
  box-shadow: none;
  background: rgba(255, 255, 255, 0.9);
}

:deep(.folder-input .el-input-group__prepend) {
  background: var(--notion-surface-soft);
  border-color: var(--notion-hairline);
  color: var(--notion-steel);
}

:deep(.folder-input .el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 3px rgba(86, 69, 212, 0.12);
}

:deep(.btn-browse.el-button) {
  padding-inline: 18px;
  border-color: var(--notion-hairline-strong);
  color: var(--notion-charcoal);
  background: var(--notion-canvas);
}

:deep(.btn-scan.el-button),
:deep(.btn-start.el-button) {
  padding-inline: 18px;
  box-shadow: none;
}

.command-status-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--notion-spacing-sm);
  margin-top: var(--notion-spacing-md);
}

.command-status-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: var(--notion-spacing-md);
  background: var(--notion-surface-soft);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-md);
}

.command-status-card__value {
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-ink);
  font-weight: 620;
}

.command-status-card__value--empty,
.summary-value--empty,
.summary-highlight-card__value--empty,
.selection-card-path--empty {
  color: var(--notion-stone);
  font-weight: 500;
}

.drop-zone-note {
  display: flex;
  gap: var(--notion-spacing-sm);
  margin-top: var(--notion-spacing-md);
  padding: var(--notion-spacing-md);
  background: linear-gradient(180deg, rgba(246, 248, 252, 0.92) 0%, rgba(255, 255, 255, 0.82) 100%);
  border: 1px dashed var(--notion-hairline-strong);
  border-radius: var(--notion-rounded-lg);
  transition: border-color var(--notion-transition-fast), background var(--notion-transition-fast), transform var(--notion-transition-fast);
}

.drop-zone-note--active {
  border-color: var(--notion-primary);
  background: rgba(86, 69, 212, 0.05);
  transform: translateY(-1px);
}

.drop-zone-note__icon {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--notion-rounded-md);
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid var(--notion-hairline);
  color: var(--notion-steel);
  flex-shrink: 0;
}

.drop-zone-note__title {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 620;
  color: var(--notion-ink);
}

.drop-zone-note__text {
  margin-top: 4px;
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-steel);
}

.drop-hint-icon {
  width: 18px;
  height: 18px;
}

.selection-summary,
.scan-summary {
  display: grid;
  gap: var(--notion-spacing-sm);
  margin-bottom: var(--notion-spacing-md);
  padding: var(--notion-spacing-md);
  background: var(--notion-surface-soft);
  border-radius: var(--notion-rounded-lg);
  border: 1px solid var(--notion-hairline);
}

.selection-summary--grid,
.scan-summary--detail {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.scan-summary--detail {
  margin-top: var(--notion-spacing-md);
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.summary-label {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-stone);
  letter-spacing: 0.04em;
}

.summary-value {
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-ink);
  font-weight: 620;
}

.summary-value--path {
  word-break: break-all;
}

.selection-list {
  display: grid;
  gap: var(--notion-spacing-sm);
}

.selection-card {
  display: block;
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
  padding: var(--notion-spacing-md);
  background: var(--notion-canvas);
}

.selection-radio {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.selection-card--active {
  border-color: rgba(86, 69, 212, 0.36);
  box-shadow: 0 0 0 3px rgba(86, 69, 212, 0.08);
  background: linear-gradient(180deg, rgba(86, 69, 212, 0.04) 0%, rgba(255, 255, 255, 0.98) 100%);
}

.selection-card-content {
  display: grid;
  gap: 10px;
}

.selection-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--notion-spacing-sm);
}

.selection-card-title {
  font-size: var(--notion-font-size-body);
  font-weight: 620;
  color: var(--notion-ink);
}

.selection-card-subtitle {
  margin-top: 4px;
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-steel);
}

.selection-card-path {
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-slate);
  word-break: break-all;
}

.selection-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--notion-spacing-sm);
  margin-top: var(--notion-spacing-md);
}

.selection-footer-text,
.action-bar__note {
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-steel);
}

.results-stack,
.scan-summary-panel {
  display: grid;
  gap: var(--notion-spacing-md);
}

.summary-highlight-card {
  padding: var(--notion-spacing-lg);
  background: linear-gradient(180deg, rgba(86, 69, 212, 0.06) 0%, rgba(255, 255, 255, 0.96) 100%);
  border: 1px solid rgba(86, 69, 212, 0.12);
  border-radius: var(--notion-rounded-lg);
}

.summary-metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--notion-spacing-sm);
}

.metric-card {
  padding: var(--notion-spacing-md);
  background: rgba(255, 255, 255, 0.84);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-md);
}

.metric-card__value {
  margin-top: 6px;
  font-size: var(--notion-font-size-body);
  font-weight: 620;
  color: var(--notion-ink);
}

.metric-card--warning {
  border-color: rgba(214, 132, 35, 0.2);
}

.metric-card--success {
  border-color: rgba(26, 174, 57, 0.18);
}

.metric-card--empty .metric-card__value {
  color: var(--notion-stone);
}

.translation-section-card__header {
  margin-bottom: var(--notion-spacing-md);
}

.action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--notion-spacing-md);
  padding: var(--notion-spacing-lg) var(--notion-spacing-xl);
  background: rgba(255, 255, 255, 0.86);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
  box-shadow: 0 16px 30px rgba(15, 23, 42, 0.04);
  backdrop-filter: blur(14px);
}

@media (max-width: 960px) {
  .scan-action-layout,
  .selection-summary--grid,
  .scan-summary--detail,
  .summary-metrics-grid,
  .section-card__header--aligned,
  .selection-footer,
  .action-bar,
  .folder-input-row {
    flex-direction: column;
  }

  .command-status-grid {
    grid-template-columns: 1fr;
  }
}

.selection-card:hover {
  border-color: var(--notion-hairline-strong);
  background: var(--notion-surface-soft);
  transform: translateY(-1px);
}

.selection-card--active {
  border-color: var(--notion-primary);
  background: rgba(86, 69, 212, 0.05);
  box-shadow: 0 0 0 3px rgba(86, 69, 212, 0.08);
}

.selection-radio {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.selection-card-content {
  padding: var(--notion-spacing-md);
}

.selection-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--notion-spacing-sm);
  margin-bottom: var(--notion-spacing-xs);
}

.selection-card-title {
  font-size: var(--notion-font-size-body);
  font-weight: 600;
  color: var(--notion-ink);
}

.selection-card-subtitle {
  margin-top: 2px;
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-steel);
}

.selection-card-path {
  margin-top: var(--notion-spacing-sm);
  padding-top: var(--notion-spacing-sm);
  border-top: 1px solid var(--notion-hairline);
  word-break: break-all;
  font-size: var(--notion-font-size-micro);
  color: var(--notion-steel);
}

.selection-footer {
  margin-top: var(--notion-spacing-md);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--notion-spacing-md);
}

.selection-footer-text,
.action-bar__note {
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-steel);
}

.results-stack {
  display: grid;
  gap: var(--notion-spacing-md);
}

.scan-summary-panel {
  display: grid;
  grid-template-columns: minmax(240px, 0.9fr) minmax(0, 1.8fr);
  gap: var(--notion-spacing-md);
}

.summary-highlight-card {
  padding: var(--notion-spacing-lg);
  background: linear-gradient(180deg, rgba(86, 69, 212, 0.06) 0%, rgba(255, 255, 255, 0.9) 100%);
  border: 1px solid rgba(86, 69, 212, 0.14);
  border-radius: var(--notion-rounded-lg);
}

.summary-metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--notion-spacing-sm);
}

.metric-card {
  padding: var(--notion-spacing-md);
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
}

.metric-card__value {
  margin-top: var(--notion-spacing-xs);
  font-size: var(--notion-font-size-body-sm);
  line-height: var(--notion-line-height-body-sm);
  color: var(--notion-ink);
  font-weight: 600;
}

.metric-card--empty .metric-card__value {
  color: var(--notion-stone);
  font-weight: 500;
}

.metric-card--warning {
  background: rgba(221, 91, 0, 0.06);
  border-color: rgba(221, 91, 0, 0.18);
}

.metric-card--success {
  background: rgba(26, 174, 57, 0.05);
  border-color: rgba(26, 174, 57, 0.16);
}

.translation-section-card__header {
  margin-bottom: var(--notion-spacing-md);
}

.action-bar {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--notion-spacing-md);
  padding: var(--notion-spacing-md) var(--notion-spacing-lg);
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
  backdrop-filter: blur(8px);
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08);
}

@media (max-width: 1080px) {
  .scan-action-layout,
  .scan-summary-panel,
  .section-card__header--aligned,
  .command-status-grid {
    grid-template-columns: 1fr;
    flex-direction: column;
  }

  .summary-metrics-grid,
  .selection-summary--grid,
  .scan-summary--detail {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .selection-footer,
  .action-bar,
  .command-surface__header,
  .results-surface__header {
    flex-direction: column;
    align-items: flex-start;
  }
}

@media (max-width: 720px) {
  .local-import-view {
    padding: var(--notion-spacing-xl) var(--notion-spacing-md) 48px;
  }

  .section-card,
  .command-surface,
  .results-surface,
  .translation-section-card {
    padding: var(--notion-spacing-lg);
  }

  .folder-input-row {
    flex-direction: column;
  }

  .summary-metrics-grid,
  .selection-summary--grid,
  .scan-summary--detail {
    grid-template-columns: 1fr;
  }

  .summary-highlight-card {
    padding: var(--notion-spacing-md);
  }
}
</style>
