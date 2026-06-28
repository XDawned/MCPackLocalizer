<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ElAlert,
  ElButton,
  ElCard,
  ElEmpty,
  ElMessage,
  ElTag,
  vLoading
} from 'element-plus'
import { getTranslationHistory, getTranslationRestoreContext } from '@/api/translate'
import { useLocalPackStore } from '@/stores/localPack'
import { useWorkflowStore } from '@/stores/workflow'

const router = useRouter()
const workflowStore = useWorkflowStore()
const localPackStore = useLocalPackStore()

const loading = ref(false)
const error = ref('')
const records = ref([])
const total = ref(0)
const restoringTaskId = ref(null)

const hasRecords = computed(() => records.value.length > 0)

function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN')
}

function getStatusMeta(status, completed) {
  if (completed) {
    return { type: 'success', label: '已完成' }
  }

  const normalized = String(status || '').trim().toLowerCase()
  if (['extracting', 'translating', 'assembling', 'paused'].includes(normalized)) {
    return { type: 'primary', label: '处理中' }
  }
  if (normalized === 'ready_to_apply') {
    return { type: 'warning', label: '待应用' }
  }
  if (normalized === 'failed') {
    return { type: 'danger', label: '失败' }
  }
  if (normalized === 'cancelled') {
    return { type: 'info', label: '已取消' }
  }
  if (normalized === 'configuring') {
    return { type: '', label: '配置中' }
  }

  return { type: 'info', label: status || '未知' }
}

function formatProgress(record) {
  const completedItems = Number(record?.completed_items || 0)
  const totalItems = Number(record?.total_items || 0)
  if (totalItems <= 0) return '—'
  return `${completedItems} / ${totalItems}`
}

function normalizeSelectedAreas(selectedAreas = [], selectableAreas = []) {
  const selectableTypes = new Set(selectableAreas.map(area => area.type))
  const normalized = Array.isArray(selectedAreas)
    ? selectedAreas.filter(type => selectableTypes.has(type))
    : []

  if (normalized.length > 0) {
    return normalized
  }

  return selectableAreas.map(area => area.type)
}

function hydrateLocalPackFromRestoreContext(restoreContext = {}) {
  const scanResult = restoreContext.scan_result
  if (!scanResult || typeof scanResult !== 'object' || Object.keys(scanResult).length === 0) {
    return
  }

  const areas = Array.isArray(scanResult.areas) ? scanResult.areas : []
  const selectableAreas = areas.filter(area => Number(area?.count || 0) > 0)
  const restoredLocalPath = restoreContext.route_query?.localPath || restoreContext.config?.local_path || ''

  localPackStore.error = null
  localPackStore.folderPath = restoredLocalPath
  localPackStore.scanResult = scanResult
  localPackStore.areas = areas
  localPackStore.selectableAreas = selectableAreas
  localPackStore.selectedAreas = normalizeSelectedAreas(restoreContext.selected_areas, selectableAreas)
  localPackStore.extractResult = null
  localPackStore.minecraftRoot = scanResult.minecraft_root || ''
  localPackStore.workRoot = scanResult.work_root || scanResult.real_path || restoredLocalPath
  localPackStore.workRootSource = scanResult.work_root_source || ''
  localPackStore.packType = scanResult.pack_type || ''
  localPackStore.versionResolutionSource = scanResult.version_resolution_source || ''
  localPackStore.recommendedAction = scanResult.recommended_action || ''
  localPackStore.selectedGameName = scanResult.game_name || scanResult.name || ''
  localPackStore.flowStage = localPackStore.FLOW_STAGE.COMPLETED
}

async function loadHistory() {
  loading.value = true
  error.value = ''

  try {
    const data = await getTranslationHistory(0, 50)
    records.value = Array.isArray(data?.items) ? data.items : []
    total.value = Number(data?.total || records.value.length || 0)
  } catch (e) {
    error.value = e?.response?.data?.detail || e?.message || '加载处理历史失败'
    records.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function handleRestore(record) {
  const taskId = record?.task_id
  if (!taskId || restoringTaskId.value) return

  restoringTaskId.value = taskId
  error.value = ''

  try {
    const restoreContext = await getTranslationRestoreContext(taskId)
    workflowStore.hydrateFromHistory(restoreContext)
    hydrateLocalPackFromRestoreContext(restoreContext)

    const targetLocation = restoreContext.current_step
      ? workflowStore.getStepLocation(restoreContext.current_step, restoreContext.route_query || {})
      : {
          path: restoreContext.recommended_route || '/workflow',
          query: restoreContext.route_query || {}
        }

    await router.push(targetLocation)
    ElMessage.success(`已恢复任务 #${taskId}`)
  } catch (e) {
    error.value = e?.response?.data?.detail || e?.message || '恢复处理历史失败'
  } finally {
    restoringTaskId.value = null
  }
}

onMounted(() => {
  loadHistory()
})
</script>

<template>
  <div class="history-view" v-loading="loading">
    <div class="page-header">
      <div>
        <h1 class="page-title">处理历史</h1>
        <p class="page-subtitle">查看先前处理记录，并恢复到推荐的页面与任务上下文。</p>
      </div>
      <ElButton class="notion-btn notion-btn--secondary" @click="loadHistory">
        刷新列表
      </ElButton>
    </div>

    <ElAlert
      v-if="error"
      :title="error"
      type="error"
      closable
      show-icon
      class="view-alert"
      @close="error = ''"
    />

    <div v-if="hasRecords" class="history-list">
      <ElCard
        v-for="record in records"
        :key="record.task_id"
        class="history-card"
        shadow="never"
      >
        <div class="history-card__header">
          <div class="history-card__title-group">
            <h2 class="history-card__title">{{ record.modpack_name || `任务 #${record.task_id}` }}</h2>
            <div class="history-card__meta-row">
              <ElTag :type="getStatusMeta(record.status, record.is_completed).type" size="small" effect="plain">
                {{ getStatusMeta(record.status, record.is_completed).label }}
              </ElTag>
              <span class="history-card__time">{{ formatDateTime(record.processed_at) }}</span>
            </div>
          </div>

          <ElButton
            class="notion-btn notion-btn--primary"
            :loading="restoringTaskId === record.task_id"
            :disabled="Boolean(restoringTaskId)"
            @click="handleRestore(record)"
          >
            恢复处理进度
          </ElButton>
        </div>

        <div class="history-card__summary-grid">
          <div class="summary-item">
            <span class="summary-label">任务 ID</span>
            <span class="summary-value summary-value--mono">{{ record.task_id }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">推荐页面</span>
            <span class="summary-value">{{ record.recommended_route || '—' }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">当前进度</span>
            <span class="summary-value">{{ formatProgress(record) }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">当前步骤</span>
            <span class="summary-value">{{ record.current_step || '—' }}</span>
          </div>
        </div>

        <div class="history-card__tags">
          <span class="tags-label">处理内容</span>
          <div v-if="Array.isArray(record.tags) && record.tags.length > 0" class="tags-list">
            <span v-for="tag in record.tags" :key="tag" class="content-tag">
              {{ tag }}
            </span>
          </div>
          <span v-else class="tags-empty">未识别处理内容</span>
        </div>
      </ElCard>
    </div>

    <div v-else class="empty-wrapper">
      <ElEmpty :description="loading ? '正在加载处理历史...' : '暂无处理历史'">
        <template #description>
          <span>{{ loading ? '正在加载处理历史...' : `暂无处理历史（共 ${total} 条）` }}</span>
        </template>
      </ElEmpty>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.history-view {
  max-width: 960px;
  margin: 0 auto;
  padding: 40px 24px 80px;
  min-height: 100%;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;

  @media (max-width: 640px) {
    flex-direction: column;
    align-items: stretch;
  }
}

.page-title {
  font-size: var(--notion-font-size-h4);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0 0 8px;
}

.page-subtitle {
  margin: 0;
  color: var(--notion-steel);
  font-size: var(--notion-font-size-body-sm);
  line-height: var(--notion-line-height-body-sm);
}

.view-alert {
  margin-bottom: 16px;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.history-card {
  border-radius: var(--notion-rounded-lg);
  border: 1px solid var(--notion-hairline);
  background: var(--notion-canvas);
}

.history-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;

  @media (max-width: 720px) {
    flex-direction: column;
    align-items: stretch;
  }
}

.history-card__title-group {
  min-width: 0;
}

.history-card__title {
  margin: 0 0 10px;
  font-size: var(--notion-font-size-h5);
  font-weight: 600;
  color: var(--notion-ink);
}

.history-card__meta-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.history-card__time {
  color: var(--notion-steel);
  font-size: var(--notion-font-size-caption);
}

.history-card__summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;

  @media (max-width: 900px) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  @media (max-width: 520px) {
    grid-template-columns: 1fr;
  }
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  border-radius: var(--notion-rounded-md);
  background: var(--fluent-surface-2);
  border: 1px solid var(--notion-hairline-soft);
}

.summary-label {
  color: var(--notion-muted);
  font-size: var(--notion-font-size-caption);
}

.summary-value {
  color: var(--notion-ink);
  font-size: var(--notion-font-size-body-sm);
  word-break: break-all;
}

.summary-value--mono {
  font-family: var(--notion-font-mono, 'Cascadia Code', 'Consolas', monospace);
}

.history-card__tags {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tags-label {
  font-size: var(--notion-font-size-caption);
  color: var(--notion-muted);
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.content-tag {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: var(--notion-rounded-full);
  background: rgba(86, 69, 212, 0.08);
  color: var(--notion-primary);
  font-size: var(--notion-font-size-caption);
  border: 1px solid rgba(86, 69, 212, 0.16);
}

.tags-empty {
  color: var(--notion-steel);
  font-size: var(--notion-font-size-body-sm);
}

.empty-wrapper {
  min-height: 360px;
  display: flex;
  align-items: center;
  justify-content: center;

  :deep(.el-empty) {
    padding: 0;
  }

  :deep(.el-empty__description) {
    color: var(--notion-steel);
    font-size: var(--notion-font-size-body-sm);
  }
}
</style>
