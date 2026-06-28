<script setup>
import { ref, computed, watch } from 'vue'
import {
  ElButton,
  ElTable,
  ElTableColumn,
  ElTag,
  ElEmpty,
  ElAlert,
  ElPopconfirm,
  ElMessage,
  ElInput,
  vLoading
} from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { useApplyStore } from '@/stores/apply'
import { useSettingsStore } from '@/stores/settings'
import { useWorkflowStore } from '@/stores/workflow'
import { downloadResourcePack } from '@/api/resourcepack'
import { getTranslateItems } from '@/api/translate'
import FileDiffPreview from '@/components/common/FileDiffPreview.vue'
import {
  asBooleanSetting,
  buildDeliveryPreview,
  formatAreaCountText,
  getAreaMeta,
  getDeliveryRootLabel,
  getI18nModStatusMeta,
  getTargetStrategyLabel,
  summarizePatchStructure,
  summarizeTaskTargets
} from '@/utils/localizationDelivery'

const route = useRoute()
const router = useRouter()
const applyStore = useApplyStore()
const settingsStore = useSettingsStore()
const workflowStore = useWorkflowStore()

const taskId = computed(() => route.query.taskId || null)
const routeModpackVersionId = computed(() => {
  const raw = route.query.modpackVersionId
  if (raw === undefined || raw === null || raw === '') return null

  const parsed = Number.parseInt(String(raw), 10)
  return Number.isNaN(parsed) ? raw : parsed
})

const applyStatus = ref('ready')
const previewLoading = ref(false)
const previewError = ref(null)
const restoreResult = ref(null)
const estimatedPreview = ref(createEmptyPreview())
const taskItems = ref([])
const patchNameInput = ref('')
const patchOutputInput = ref('')

const pageLoading = computed(() => {
  return previewLoading.value || applyStore.loading || applyStore.applying || applyStore.restoring || applyStore.generating
})

const hasScopedBackups = computed(() => {
  return routeModpackVersionId.value !== null || applyStore.lastAppliedBackup !== null
})

const backupPreviewRecord = computed(() => {
  if (applyStore.lastAppliedBackup?.id) {
    return applyStore.backups.find(item => item.id === applyStore.lastAppliedBackup.id) || applyStore.lastAppliedBackup
  }

  if (hasScopedBackups.value) {
    return applyStore.backups[0] || null
  }

  return null
})

const fileChanges = computed(() => {
  const backupRecord = backupPreviewRecord.value
  const fallbackPreview = estimatedPreview.value

  if (!backupRecord) {
    return {
      modified: fallbackPreview.modifiedFiles,
      added: fallbackPreview.addedFiles
    }
  }

  const modified = (backupRecord.backed_files || []).map(path => {
    const meta = fallbackPreview.pathMeta[path] || {}
    return {
      path,
      original_size: meta.original_size ?? 0,
      new_size: meta.new_size ?? meta.size ?? 0
    }
  })

  const added = (backupRecord.added_files || []).map(path => {
    const meta = fallbackPreview.pathMeta[path] || {}
    return {
      path,
      size: meta.size ?? meta.new_size ?? 0
    }
  })

  return { modified, added }
})

const totalFiles = computed(() => fileChanges.value.modified.length + fileChanges.value.added.length)
const totalItems = computed(() => estimatedPreview.value.itemCount)
const previewSourceLabel = computed(() => {
  return backupPreviewRecord.value ? '基于备份记录' : '基于后端真实 target_path 汇总'
})
const canRestore = computed(() => Boolean(backupPreviewRecord.value?.id))
const resourcePackInfo = computed(() => applyStore.resourcePack)
const patchPackageInfo = computed(() => applyStore.patchPackage)
const patchStructure = computed(() => summarizePatchStructure(patchPackageInfo.value || {}))
const patchTargetsSummary = computed(() => summarizeTaskTargets(taskItems.value))
const patchTargetSamples = computed(() => patchTargetsSummary.value.sampleTargets || [])
const patchAreaCounts = computed(() => patchTargetsSummary.value.areaCounts || [])
const patchStrategyCounts = computed(() => patchTargetsSummary.value.strategyCounts || [])
const patchTargetRoots = computed(() => patchTargetsSummary.value.targetRoots || [])
const includeI18nUpdateMod = computed(() => asBooleanSetting(settingsStore.settings?.include_i18n_update_mod, false))
const i18nModStatusMeta = computed(() => getI18nModStatusMeta(patchPackageInfo.value?.i18n_mod || {}))

const statusConfig = computed(() => {
  if (applyStatus.value === 'applied') return { type: 'success', label: '已应用' }
  if (applyStatus.value === 'restored') return { type: 'info', label: '已恢复' }
  return { type: 'warning', label: '待应用' }
})

function createEmptyPreview() {
  return {
    modifiedFiles: [],
    addedFiles: [],
    pathMeta: {},
    itemCount: 0
  }
}

function formatBytes(bytes) {
  const value = Number(bytes || 0)
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(2)} MB`
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${value} B`
}

function formatTime(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN')
}

function formatBackupStatus(status) {
  if (status === 'active') return '可恢复'
  if (status === 'restored') return '已恢复'
  return status || '—'
}

function backupStatusType(status) {
  if (status === 'active') return 'success'
  if (status === 'restored') return 'info'
  return 'warning'
}

async function fetchAllTaskItems(currentTaskId) {
  const limit = 500
  const collected = []
  let total = 0
  let offset = 0

  do {
    const data = await getTranslateItems(currentTaskId, offset, limit)
    const pageItems = Array.isArray(data?.items) ? data.items : []
    total = Number(data?.total || 0)
    collected.push(...pageItems)
    offset += pageItems.length

    if (pageItems.length === 0) break
  } while (collected.length < total)

  return collected
}

function syncApplyStatus() {
  if (restoreResult.value) {
    applyStatus.value = 'restored'
    return
  }

  if (applyStore.activeBackup && (hasScopedBackups.value || applyStore.lastAppliedBackup)) {
    applyStatus.value = 'applied'
    return
  }

  if (backupPreviewRecord.value?.status === 'restored') {
    applyStatus.value = 'restored'
    return
  }

  applyStatus.value = 'ready'
}

async function loadPreview(currentTaskId) {
  previewLoading.value = true
  previewError.value = null

  try {
    const items = await fetchAllTaskItems(currentTaskId)
    taskItems.value = items
    estimatedPreview.value = buildDeliveryPreview(items)
  } catch (error) {
    previewError.value = error?.response?.data?.detail || error?.message || '加载文件变更预览失败'
    taskItems.value = []
    estimatedPreview.value = createEmptyPreview()
  } finally {
    previewLoading.value = false
  }
}

function syncWorkflowContext() {
  workflowStore.updateRouteContext({
    taskId: taskId.value,
    modpackVersionId: route.query.modpackVersionId,
    localPath: route.query.localPath,
    scanId: route.query.scanId
  })
}

function handleGoBack() {
  syncWorkflowContext()
  router.push(workflowStore.getBackLocation(4))
}

async function initializeView() {
  applyStore.reset()
  restoreResult.value = null
  previewError.value = null
  estimatedPreview.value = createEmptyPreview()
  taskItems.value = []
  applyStatus.value = 'ready'
  patchNameInput.value = ''
  patchOutputInput.value = settingsStore.settings?.patch_output_dir || ''

  syncWorkflowContext()

  if (!taskId.value) return

  await Promise.all([
    settingsStore.loadSettings(),
    applyStore.loadBackups(routeModpackVersionId.value),
    loadPreview(taskId.value)
  ])

  patchOutputInput.value = settingsStore.settings?.patch_output_dir || ''
  syncApplyStatus()
}

async function handleApply() {
  if (!taskId.value) return

  try {
    const result = await applyStore.applyTranslation(taskId.value)
    restoreResult.value = null
    applyStatus.value = 'applied'
    ElMessage.success(result?.id ? `汉化已应用，已创建备份 #${result.id}` : '汉化已应用')
  } catch {
    // error handled by store
  }
}

async function handleRestore(backupId = backupPreviewRecord.value?.id) {
  if (!backupId) return

  try {
    const result = await applyStore.restoreBackup(backupId)
    restoreResult.value = result || null
    applyStatus.value = 'restored'
    const restoredCount = result?.restored_files?.length || 0
    const removedCount = result?.removed_files?.length || 0
    ElMessage.success(`恢复完成：还原 ${restoredCount} 个文件，移除 ${removedCount} 个文件`)
  } catch {
    // error handled by store
  }
}

async function handleDeleteBackup(backupId) {
  try {
    await applyStore.deleteBackup(backupId)
    syncApplyStatus()
    ElMessage.success('备份已删除')
  } catch {
    // error handled by store
  }
}

async function handleGenerateResourcePack() {
  if (!taskId.value) return

  try {
    const result = await applyStore.generateResourcePack(taskId.value, {})
    ElMessage.success(result?.filename ? `资源包已生成：${result.filename}` : '资源包已生成')
  } catch {
    // error handled by store
  }
}

async function handleGeneratePatchPackage() {
  if (!taskId.value) return

  try {
    const payload = {
      name: patchNameInput.value.trim() || null,
      output_dir: patchOutputInput.value.trim() || null
    }
    const result = await applyStore.generatePatchPackage(taskId.value, payload)
    ElMessage.success(result?.patch_path ? `补丁目录已生成：${result.patch_path}` : '补丁目录已生成')
  } catch {
    // error handled by store
  }
}

async function handleDownloadResourcePack() {
  if (!taskId.value || !applyStore.hasResourcePack) return

  try {
    const result = await downloadResourcePack(taskId.value)
    const blob = result?.data || result
    const filename = result?.filename || resourcePackInfo.value?.filename || `MCPackLocalizer_${taskId.value}.zip`
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('资源包开始下载')
  } catch (error) {
    ElMessage.error(`资源包下载失败：${error?.message || '未知错误'}`)
  }
}

watch([taskId, routeModpackVersionId], initializeView, { immediate: true })
</script>

<template>
  <div class="apply-view" v-loading="pageLoading">
    <ElEmpty
      v-if="!taskId"
      description="未指定翻译任务"
      style="margin-top: 80px;"
    />

    <template v-else>
      <div class="page-header">
        <h1 class="page-title">汉化应用</h1>
      </div>

      <ElAlert
        v-if="applyStore.error"
        :title="applyStore.error"
        type="error"
        closable
        show-icon
        class="view-alert"
      />

      <ElAlert
        v-if="previewError"
        :title="previewError"
        type="warning"
        closable
        show-icon
        class="view-alert"
      />

      <div class="apply-content">
        <div class="notion-card summary-card">
          <div class="summary-header">
            <h3 class="summary-title">任务概览</h3>
            <ElTag :type="statusConfig.type" size="large">
              {{ statusConfig.label }}
            </ElTag>
          </div>
          <div class="summary-meta">
            <div class="summary-item">
              <span class="summary-label">任务 ID</span>
              <span class="summary-value summary-value--mono">{{ taskId }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">变更文件数</span>
              <span class="summary-value summary-value--accent">{{ totalFiles }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">翻译条目数</span>
              <span class="summary-value">{{ totalItems }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">备份记录</span>
              <span class="summary-value">{{ applyStore.backups.length }}</span>
            </div>
          </div>
        </div>

        <div class="notion-card">
          <div class="section-header">
            <h3 class="section-title">文件应用操作</h3>
            <span class="section-badge">自动读取已保存的本地路径</span>
          </div>

          <div class="action-row">
            <ElButton
              class="notion-btn notion-btn--secondary notion-btn--lg"
              @click="handleGoBack"
            >
              返回上一步
            </ElButton>
            <ElButton
              class="notion-btn notion-btn--primary notion-btn--lg"
              :loading="applyStore.applying"
              :disabled="applyStore.applying"
              @click="handleApply"
            >
              应用翻译
            </ElButton>

            <ElPopconfirm
              title="确定要恢复原始文件吗？所有汉化更改将被撤销。"
              @confirm="handleRestore()"
            >
              <template #reference>
                <ElButton
                  class="notion-btn notion-btn--warn notion-btn--lg"
                  :loading="applyStore.restoring"
                  :disabled="!canRestore || applyStore.restoring"
                >
                  还原最新备份
                </ElButton>
              </template>
            </ElPopconfirm>
          </div>
        </div>

        <div class="notion-card targets-card">
          <div class="section-header">
            <h3 class="section-title">真实目标落点</h3>
            <span class="section-badge">基于 `area_type` / `target_strategy` / `target_path`</span>
          </div>

          <div class="targets-grid">
            <div class="target-summary-block">
              <span class="summary-label">区域类型</span>
              <div class="badge-list">
                <span v-for="area in patchAreaCounts" :key="area.type" class="inline-badge">
                  {{ area.label }} · {{ area.count }}
                </span>
              </div>
            </div>
            <div class="target-summary-block">
              <span class="summary-label">目标策略</span>
              <div class="badge-list">
                <span v-for="strategy in patchStrategyCounts" :key="strategy.strategy" class="inline-badge inline-badge--muted">
                  {{ strategy.label }} · {{ strategy.count }}
                </span>
              </div>
            </div>
            <div class="target-summary-block">
              <span class="summary-label">交付根目录</span>
              <div class="badge-list">
                <span v-for="root in patchTargetRoots" :key="root.root" class="inline-badge inline-badge--soft">
                  {{ root.label }} · {{ root.count }}
                </span>
              </div>
            </div>
          </div>

          <div v-if="patchTargetSamples.length > 0" class="target-sample-list">
            <div v-for="sample in patchTargetSamples" :key="sample.path" class="target-sample-item">
              <div class="target-sample-main">
                <span class="target-path">{{ sample.path }}</span>
                <span class="target-meta">
                  {{ getAreaMeta(sample.areaType).label }} / {{ getTargetStrategyLabel(sample.targetStrategy) }}
                </span>
              </div>
              <span class="target-source">{{ sample.sourceFile || '—' }}</span>
            </div>
          </div>

          <ElEmpty
            v-else
            description="暂无可展示的目标落点"
            :image-size="72"
          />
        </div>

        <div class="notion-card patch-card">
          <div class="section-header section-header--between">
            <div>
              <h3 class="section-title">整合包补丁目录</h3>
              <p class="section-desc">生成贴近示例补丁的目录交付件，重点覆盖 `config/`、`kubejs/`、`mods/`，并预留空 `resourcepacks/`。</p>
            </div>
            <span class="section-badge">{{ applyStore.hasPatchPackage ? '已生成' : '未生成' }}</span>
          </div>

          <div class="patch-form-grid">
            <div class="patch-form-field">
              <span class="summary-label">补丁名称</span>
              <ElInput v-model="patchNameInput" placeholder="留空则由后端自动生成目录名" />
            </div>
            <div class="patch-form-field">
              <span class="summary-label">输出目录</span>
              <ElInput v-model="patchOutputInput" placeholder="留空则使用后端设置中的 patch_output_dir 或默认工作区" />
            </div>
          </div>

          <div class="delivery-settings">
            <div class="delivery-settings-item">
              <span class="summary-label">附带 I18nUpdateMod</span>
              <ElTag :type="includeI18nUpdateMod ? 'success' : 'info'" size="small">
                {{ includeI18nUpdateMod ? '已启用' : '未启用' }}
              </ElTag>
            </div>
            <div class="delivery-settings-item">
              <span class="summary-label">默认输出目录</span>
              <span class="delivery-settings-value">{{ settingsStore.settings?.patch_output_dir || '后端默认目录' }}</span>
            </div>
          </div>

          <div class="action-row action-row--compact">
            <ElButton
              class="notion-btn notion-btn--primary notion-btn--lg"
              :loading="applyStore.isGeneratingPatch"
              :disabled="applyStore.generating"
              @click="handleGeneratePatchPackage"
            >
              生成补丁目录
            </ElButton>
          </div>

          <div class="structure-grid">
            <div v-for="root in patchStructure" :key="root.root" class="structure-item">
              <div class="structure-item-head">
                <span class="structure-item-title">{{ getDeliveryRootLabel(root.root) }}</span>
                <ElTag :type="root.reserved ? 'info' : 'success'" size="small">
                  {{ root.reserved ? '预留' : '已写入' }}
                </ElTag>
              </div>
              <span class="structure-item-count">{{ root.writtenCount }} 个文件</span>
            </div>
          </div>

          <div v-if="patchPackageInfo" class="patch-result-panel">
            <div class="resourcepack-grid">
              <div class="summary-item">
                <span class="summary-label">补丁路径</span>
                <span class="summary-value summary-value--file">{{ patchPackageInfo.patch_path || '—' }}</span>
              </div>
              <div class="summary-item">
                <span class="summary-label">写入文件</span>
                <span class="summary-value">{{ patchPackageInfo.file_count || 0 }}</span>
              </div>
              <div class="summary-item">
                <span class="summary-label">预留目录</span>
                <span class="summary-value">{{ (patchPackageInfo.placeholder_directories || []).length }}</span>
              </div>
              <div class="summary-item">
                <span class="summary-label">resourcepacks 状态</span>
                <span class="summary-value">{{ patchPackageInfo.resourcepacks_reserved_only ? '仅空目录预留' : '含真实内容' }}</span>
              </div>
            </div>

            <div class="i18n-mod-panel">
              <div class="i18n-mod-header">
                <span class="summary-label">I18nUpdateMod 处理结果</span>
                <ElTag :type="i18nModStatusMeta.type" size="small">{{ i18nModStatusMeta.label }}</ElTag>
              </div>
              <p class="i18n-mod-message">{{ patchPackageInfo.i18n_mod?.message || '后端未返回额外提示' }}</p>
              <div v-if="patchPackageInfo.i18n_mod?.file_path || patchPackageInfo.i18n_mod?.filename" class="i18n-mod-meta">
                <span>{{ patchPackageInfo.i18n_mod?.filename || '—' }}</span>
                <span>{{ patchPackageInfo.i18n_mod?.file_path || '—' }}</span>
              </div>
            </div>

            <div v-if="(patchPackageInfo.written_files || []).length > 0" class="path-list-block">
              <span class="summary-label">已写入文件</span>
              <ul class="path-list">
                <li v-for="path in patchPackageInfo.written_files" :key="path">{{ path }}</li>
              </ul>
            </div>

            <div v-if="(patchPackageInfo.skipped_resourcepack_targets || []).length > 0" class="path-list-block">
              <span class="summary-label">当前阶段跳过的资源包目标</span>
              <ul class="path-list">
                <li v-for="path in patchPackageInfo.skipped_resourcepack_targets" :key="path">{{ path }}</li>
              </ul>
            </div>
          </div>
        </div>

        <div class="notion-card resourcepack-card">
          <div class="section-header section-header--between">
            <div>
              <h3 class="section-title">资源包导出</h3>
              <p class="section-desc">此处仅保留旧资源包 ZIP 导出流程，适合传统 `assets/.../lang` 交付。与上方“整合包补丁目录”是两条不同路径。</p>
            </div>
            <span class="section-badge">{{ applyStore.hasResourcePack ? '已生成，可下载' : '未生成' }}</span>
          </div>

          <div class="action-row action-row--compact">
            <ElButton
              class="notion-btn notion-btn--secondary notion-btn--lg"
              :loading="applyStore.isGeneratingResourcePack"
              :disabled="applyStore.generating"
              @click="handleGenerateResourcePack"
            >
              生成资源包
            </ElButton>
            <ElButton
              class="notion-btn notion-btn--secondary notion-btn--lg"
              :disabled="!applyStore.hasResourcePack || applyStore.generating"
              @click="handleDownloadResourcePack"
            >
              下载资源包
            </ElButton>
          </div>

          <div v-if="resourcePackInfo" class="resourcepack-preview">
            <div class="resourcepack-grid">
              <div class="summary-item">
                <span class="summary-label">文件名</span>
                <span class="summary-value summary-value--file">{{ resourcePackInfo.filename || '—' }}</span>
              </div>
              <div class="summary-item">
                <span class="summary-label">文件大小</span>
                <span class="summary-value">{{ formatBytes(resourcePackInfo.file_size) }}</span>
              </div>
              <div class="summary-item">
                <span class="summary-label">条目数量</span>
                <span class="summary-value">{{ resourcePackInfo.item_count || 0 }}</span>
              </div>
              <div class="summary-item">
                <span class="summary-label">Pack Format</span>
                <span class="summary-value">{{ resourcePackInfo.pack_format || '—' }}</span>
              </div>
            </div>
          </div>

          <ElEmpty
            v-else
            description="生成资源包后可在此查看文件信息并下载"
            :image-size="72"
          />
        </div>

        <div class="notion-card changes-card">
          <div class="section-header">
            <h3 class="section-title">文件变更预览</h3>
            <span class="section-badge">{{ previewSourceLabel }}</span>
          </div>

          <FileDiffPreview
            :added-files="fileChanges.added"
            :modified-files="fileChanges.modified"
            :loading="previewLoading"
          />
        </div>

        <div class="notion-card backups-card">
          <div class="section-header">
            <h3 class="section-title">备份记录</h3>
            <span class="section-badge">共 {{ applyStore.backups.length }} 条</span>
          </div>

          <ElEmpty
            v-if="!applyStore.loading && applyStore.backups.length === 0"
            description="暂无备份记录"
            :image-size="80"
          />

          <ElTable
            v-else
            :data="applyStore.backups"
            row-key="id"
            size="small"
            class="backups-table"
            :header-cell-style="{ background: 'var(--notion-surface)', color: 'var(--notion-steel)', fontSize: '12px', fontWeight: '500', borderColor: 'var(--notion-hairline)' }"
            :cell-style="{ color: 'var(--notion-ink)', fontSize: '13px', borderColor: 'var(--notion-hairline)' }"
          >
            <ElTableColumn prop="id" label="备份ID" width="110" />
            <ElTableColumn prop="modpack_version_id" label="整合包版本" min-width="120">
              <template #default="{ row }">
                {{ row.modpack_version_id ?? '—' }}
              </template>
            </ElTableColumn>
            <ElTableColumn prop="status" label="状态" width="110">
              <template #default="{ row }">
                <ElTag :type="backupStatusType(row.status)" size="small">
                  {{ formatBackupStatus(row.status) }}
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn label="覆盖文件" width="100" align="center">
              <template #default="{ row }">
                {{ row.backed_files?.length || 0 }}
              </template>
            </ElTableColumn>
            <ElTableColumn label="新增文件" width="100" align="center">
              <template #default="{ row }">
                {{ row.added_files?.length || 0 }}
              </template>
            </ElTableColumn>
            <ElTableColumn prop="created_at" label="创建时间" min-width="180">
              <template #default="{ row }">
                {{ formatTime(row.created_at) }}
              </template>
            </ElTableColumn>
            <ElTableColumn label="操作" width="180" align="center">
              <template #default="{ row }">
                <div class="table-actions">
                  <ElPopconfirm
                    title="确定要恢复此备份吗？"
                    @confirm="handleRestore(row.id)"
                  >
                    <template #reference>
                      <ElButton
                        class="notion-btn notion-btn--table"
                        size="small"
                        :loading="applyStore.isRestoringBackup(row.id)"
                        :disabled="applyStore.restoring"
                      >
                        恢复
                      </ElButton>
                    </template>
                  </ElPopconfirm>

                  <ElPopconfirm
                    title="确定要删除此备份吗？"
                    @confirm="handleDeleteBackup(row.id)"
                  >
                    <template #reference>
                      <ElButton
                        class="notion-btn notion-btn--table-danger"
                        size="small"
                        :loading="applyStore.isDeletingBackup(row.id)"
                        :disabled="applyStore.isDeletingBackup(row.id)"
                      >
                        删除
                      </ElButton>
                    </template>
                  </ElPopconfirm>
                </div>
              </template>
            </ElTableColumn>
          </ElTable>
        </div>
      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.apply-view {
  max-width: 960px;
  margin: 0 auto;
  padding: var(--notion-spacing-xxl) var(--notion-spacing-xl) 64px;
}

.view-alert {
  margin-bottom: var(--notion-spacing-lg);
}

.page-header {
  margin-bottom: var(--notion-spacing-xxl);
}

.page-title {
  font-size: var(--notion-font-size-h3);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0;
  letter-spacing: var(--notion-ls-h1);
}

.apply-content {
  display: flex;
  flex-direction: column;
  gap: var(--notion-spacing-md);
}

.notion-card {
  background: var(--notion-canvas);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
  padding: var(--notion-spacing-xl);
}

.summary-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--notion-spacing-sm);
  margin-bottom: var(--notion-spacing-md);
}

.summary-title {
  font-size: var(--notion-font-size-h5);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0;
}

.summary-meta,
.resourcepack-grid,
.targets-grid,
.patch-form-grid,
.structure-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--notion-spacing-md);
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: var(--notion-spacing-xxs);
  min-width: 0;
}

.summary-label {
  font-size: var(--notion-font-size-micro-uppercase);
  font-weight: 600;
  color: var(--notion-stone);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.summary-value {
  font-size: var(--notion-font-size-h5);
  font-weight: 700;
  color: var(--notion-ink);
}

.summary-value--mono,
.summary-value--file,
.delivery-settings-value,
.target-path,
.target-source {
  font-family: 'JetBrains Mono', 'Cascadia Code', 'Consolas', 'Monaco', monospace;
  font-size: var(--notion-font-size-caption);
  line-height: 1.5;
  word-break: break-all;
}

.summary-value--accent {
  color: var(--notion-brand-green);
}

.section-header {
  display: flex;
  align-items: center;
  gap: var(--notion-spacing-sm);
  margin-bottom: var(--notion-spacing-md);
}

.section-header--between {
  justify-content: space-between;
  align-items: flex-start;
}

.section-title {
  font-size: var(--notion-font-size-h5);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0;
}

.section-desc {
  margin: 6px 0 0;
  font-size: var(--notion-font-size-caption);
  color: var(--notion-steel);
  line-height: var(--notion-line-height-caption);
}

.section-badge {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-steel);
  background: var(--notion-surface);
  padding: 2px 8px;
  border-radius: var(--notion-rounded-sm);
  border: 1px solid var(--notion-hairline);
}

.action-row {
  display: flex;
  gap: var(--notion-spacing-sm);
  flex-wrap: wrap;
}

.action-row--compact {
  margin-bottom: var(--notion-spacing-md);
}

.notion-btn {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 500;
  border-radius: var(--notion-rounded-md);
  padding: 8px 18px;
  height: auto;
  line-height: var(--notion-line-height-button);
  transition: all var(--notion-transition-normal);
  border: 1px solid transparent;
}

.notion-btn--lg {
  padding: 10px 18px;
  font-size: var(--notion-font-size-body);
  flex: 1;
  min-width: 180px;
  height: 44px;
}

.notion-btn--primary {
  background: var(--notion-primary);
  border-color: var(--notion-primary);
  color: var(--notion-on-primary);

  &:hover {
    background: var(--notion-primary-pressed);
    border-color: var(--notion-primary-pressed);
    color: var(--notion-on-primary);
  }

  &.is-disabled,
  &[disabled] {
    background: var(--notion-hairline);
    border-color: var(--notion-hairline);
    color: var(--notion-muted);
  }
}

.notion-btn--warn {
  background: transparent;
  border-color: var(--notion-brand-orange);
  color: var(--notion-brand-orange);

  &:hover {
    background: var(--notion-brand-orange);
    border-color: var(--notion-brand-orange);
    color: #fff;
  }
}

.notion-btn--secondary,
.notion-btn--table {
  background: transparent;
  border-color: var(--notion-hairline-strong);
  color: var(--notion-ink);

  &:hover {
    background: var(--notion-surface);
    border-color: var(--notion-steel);
    color: var(--notion-ink);
  }
}

.notion-btn--table-danger {
  font-size: var(--notion-font-size-micro);
  font-weight: 500;
  background: transparent;
  border: none;
  color: var(--notion-steel);
  padding: 2px 6px;
  height: auto;
  line-height: var(--notion-line-height-caption);
  border-radius: var(--notion-rounded-sm);

  &:hover {
    color: var(--notion-semantic-error);
    background: transparent;
  }
}

.target-summary-block,
.patch-form-field,
.structure-item,
.delivery-settings-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  background: var(--fluent-surface-2);
  border: 1px solid var(--notion-hairline-soft);
  border-radius: var(--notion-rounded-md);
}

.badge-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.inline-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--notion-surface);
  border: 1px solid var(--notion-hairline);
  color: var(--notion-charcoal);
  font-size: var(--notion-font-size-micro);
}

.inline-badge--muted {
  color: var(--notion-ink);
}

.inline-badge--soft {
  color: var(--notion-steel);
}

.target-sample-list,
.path-list-block {
  margin-top: var(--notion-spacing-md);
}

.target-sample-item {
  display: flex;
  justify-content: space-between;
  gap: var(--notion-spacing-md);
  padding: 12px 0;
  border-top: 1px solid var(--notion-hairline-soft);
}

.target-sample-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.target-meta {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-steel);
}

.delivery-settings {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--notion-spacing-sm);
  margin-bottom: var(--notion-spacing-md);
}

.structure-item-head,
.i18n-mod-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.structure-item-title {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 600;
  color: var(--notion-ink);
}

.structure-item-count {
  font-size: var(--notion-font-size-caption);
  color: var(--notion-steel);
}

.patch-result-panel,
.resourcepack-preview {
  margin-top: var(--notion-spacing-md);
  padding-top: var(--notion-spacing-md);
  border-top: 1px solid var(--notion-hairline);
}

.i18n-mod-panel {
  margin-top: var(--notion-spacing-md);
  padding: 14px 16px;
  background: var(--fluent-surface-2);
  border: 1px solid var(--notion-hairline-soft);
  border-radius: var(--notion-rounded-md);
}

.i18n-mod-message {
  margin: 10px 0 0;
  font-size: var(--notion-font-size-caption);
  color: var(--notion-ink);
  line-height: var(--notion-line-height-caption);
}

.i18n-mod-meta {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: var(--notion-font-size-micro);
  color: var(--notion-steel);
}

.path-list {
  margin: 8px 0 0;
  padding-left: 18px;
  color: var(--notion-charcoal);
  font-size: var(--notion-font-size-caption);
  line-height: 1.6;
}

.changes-card,
.backups-card,
.resourcepack-card,
.patch-card,
.targets-card {
  overflow: hidden;
}

.table-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.backups-table {
  :deep(.el-table) {
    background: transparent;
  }

  :deep(.el-table__header-wrapper) {
    border-radius: var(--notion-rounded-md) var(--notion-rounded-md) 0 0;
  }

  :deep(.el-table__body-wrapper) {
    border-radius: 0 0 var(--notion-rounded-md) var(--notion-rounded-md);
  }

  :deep(.el-table__row:hover > td) {
    background: rgba(0, 0, 0, 0.02);
  }

  :deep(.el-table__inner-wrapper::before) {
    display: none;
  }
}

@media (max-width: 640px) {
  .apply-view {
    padding: var(--notion-spacing-xl) var(--notion-spacing-md) 48px;
  }

  .summary-header,
  .section-header,
  .section-header--between,
  .target-sample-item {
    align-items: flex-start;
    flex-direction: column;
  }

  .notion-btn--lg {
    min-width: 100%;
  }

  .table-actions {
    flex-direction: column;
    width: 100%;
  }
}
</style>
