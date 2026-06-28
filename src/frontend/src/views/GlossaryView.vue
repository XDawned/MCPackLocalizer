<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import {
  ElButton, ElInput, ElTable, ElTableColumn, ElTag, ElEmpty,
  ElAlert, ElDialog, ElForm, ElFormItem,   ElSwitch,
  ElPopconfirm, ElMessage
} from 'element-plus'
import { useGlossaryStore } from '@/stores/glossary'

const glossaryStore = useGlossaryStore()

const modalVisible = ref(false)
const importModalVisible = ref(false)
const editingEntry = ref(null)
const isSubmitting = ref(false)
const importContent = ref('')
const importing = ref(false)

let searchTimer = null

const formData = reactive({
  source_term: '',
  target_term: '',
  category: '',
  is_regex: false
})

const modalTitle = computed(() => editingEntry.value ? '编辑术语' : '添加术语')

function sourceTagType(source) {
  if (source === 'CFPA' || source === 'cfpa') return 'success'
  return ''
}

function sourceTagLabel(source) {
  if (source === 'CFPA' || source === 'cfpa') return 'CFPA'
  return '手动'
}

function formatDate(isoStr) {
  if (!isoStr) return ''
  try {
    const d = new Date(isoStr)
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
  } catch {
    return isoStr
  }
}

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    glossaryStore.loadEntries(glossaryStore.search, 0, 50)
  }, 300)
}

function openAddModal() {
  editingEntry.value = null
  formData.source_term = ''
  formData.target_term = ''
  formData.category = ''
  formData.is_regex = false
  modalVisible.value = true
}

function openEditModal(entry) {
  editingEntry.value = entry
  formData.source_term = entry.source_term || ''
  formData.target_term = entry.target_term || ''
  formData.category = entry.category || ''
  formData.is_regex = !!entry.is_regex
  modalVisible.value = true
}

function closeModal() {
  modalVisible.value = false
}

async function handleSubmit() {
  if (!formData.source_term.trim() || !formData.target_term.trim()) {
    ElMessage.warning('请填写源术语和目标术语')
    return
  }
  isSubmitting.value = true
  try {
    const payload = {
      source_term: formData.source_term.trim(),
      target_term: formData.target_term.trim(),
      category: formData.category.trim(),
      is_regex: formData.is_regex
    }
    if (editingEntry.value) {
      await glossaryStore.updateEntry(editingEntry.value.id, payload)
      ElMessage.success('术语更新成功')
    } else {
      await glossaryStore.createEntry(payload)
      ElMessage.success('术语添加成功')
    }
    modalVisible.value = false
  } catch {
    ElMessage.error(glossaryStore.error || '操作失败')
  } finally {
    isSubmitting.value = false
  }
}

async function handleDelete(id) {
  try {
    await glossaryStore.deleteEntry(id)
    ElMessage.success('术语已删除')
  } catch {
    ElMessage.error(glossaryStore.error || '删除失败')
  }
}

function openImportModal() {
  importContent.value = ''
  importModalVisible.value = true
}

async function handleImport() {
  if (!importContent.value.trim()) {
    ElMessage.warning('请粘贴导入数据')
    return
  }
  importing.value = true
  try {
    const result = await glossaryStore.importFromCFPA({ content: importContent.value.trim() })
    importModalVisible.value = false
    ElMessage.success(`成功导入 ${result?.count || 0} 条术语`)
    glossaryStore.loadEntries(glossaryStore.search, 0, 50)
  } catch {
    ElMessage.error(glossaryStore.error || '导入失败')
  } finally {
    importing.value = false
  }
}

onMounted(() => {
  glossaryStore.loadEntries('', 0, 50)
})

onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<template>
  <div class="glossary-view">
    <!-- Page Header -->
    <h2 class="page-title">术语库管理</h2>
    <p class="page-desc">管理 Minecraft 翻译术语，确保 AI 翻译一致性</p>

    <!-- Error Alert -->
    <ElAlert
      v-if="glossaryStore.error"
      :title="glossaryStore.error"
      type="error"
      show-icon
      closable
      class="error-alert"
      @close="glossaryStore.error = null"
    />

    <!-- Toolbar -->
    <div class="toolbar">
      <div class="toolbar-left">
        <ElInput
          v-model="glossaryStore.search"
          placeholder="搜索术语..."
          class="search-input"
          @input="onSearchInput"
        >
          <template #prefix>
            <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
          </template>
        </ElInput>
        <span v-if="glossaryStore.total > 0" class="entry-count">
          共 {{ glossaryStore.total }} 条术语
        </span>
      </div>
      <div class="toolbar-right">
        <ElButton type="primary" class="btn-add" @click="openAddModal">
          <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 5v14" />
            <path d="M5 12h14" />
          </svg>
          添加术语
        </ElButton>
        <ElButton class="btn-import" @click="openImportModal">
          <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          导入 CFPA
        </ElButton>
      </div>
    </div>

    <!-- Table -->
    <div class="table-container" v-loading="glossaryStore.loading">
      <ElEmpty
        v-if="!glossaryStore.loading && glossaryStore.entries.length === 0 && !glossaryStore.search"
        description="暂无术语数据，点击「添加术语」开始添加"
        class="empty-state"
      />
      <ElEmpty
        v-else-if="!glossaryStore.loading && glossaryStore.entries.length === 0 && glossaryStore.search"
        :description="`未找到匹配「${glossaryStore.search}」的术语`"
        class="empty-state"
      />
      <ElTable
        v-else
        :data="glossaryStore.entries"
        row-key="id"
        class="terms-table"
        size="small"
      >
        <ElTableColumn prop="source_term" label="源术语" min-width="140">
          <template #default="{ row }">
            <code class="col-code">{{ row.source_term }}</code>
          </template>
        </ElTableColumn>

        <ElTableColumn prop="target_term" label="目标术语" min-width="140">
          <template #default="{ row }">
            <span class="col-target">{{ row.target_term }}</span>
          </template>
        </ElTableColumn>

        <ElTableColumn prop="category" label="分类" min-width="100">
          <template #default="{ row }">
            <ElTag v-if="row.category" size="small" class="tag-category">{{ row.category }}</ElTag>
            <span v-else class="text-muted">—</span>
          </template>
        </ElTableColumn>

        <ElTableColumn prop="source" label="来源" width="80">
          <template #default="{ row }">
            <ElTag size="small" :type="sourceTagType(row.source)" class="tag-source">
              {{ sourceTagLabel(row.source) }}
            </ElTag>
          </template>
        </ElTableColumn>

        <ElTableColumn prop="is_regex" label="正则" width="70">
          <template #default="{ row }">
            <ElTag size="small" :type="row.is_regex ? 'success' : 'info'" class="tag-regex">
              {{ row.is_regex ? '是' : '否' }}
            </ElTag>
          </template>
        </ElTableColumn>

        <ElTableColumn prop="created_at" label="创建时间" width="120">
          <template #default="{ row }">
            <span class="col-date">{{ formatDate(row.created_at) }}</span>
          </template>
        </ElTableColumn>

        <ElTableColumn label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <ElButton size="small" text class="btn-action" @click="openEditModal(row)">
                <svg class="action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                </svg>
              </ElButton>
              <ElPopconfirm
                title="确定要删除此术语吗？此操作不可撤销。"
                confirm-button-text="删除"
                cancel-button-text="取消"
                @confirm="handleDelete(row.id)"
              >
                <template #reference>
                  <ElButton size="small" text type="danger" class="btn-action">
                    <svg class="action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                  </ElButton>
                </template>
              </ElPopconfirm>
            </div>
          </template>
        </ElTableColumn>
      </ElTable>
    </div>

    <!-- Add/Edit Dialog -->
    <ElDialog v-model="modalVisible" :title="modalTitle" width="480px" @close="closeModal">
      <ElForm :model="formData" class="entry-form">
        <ElFormItem label="源术语" required>
          <ElInput v-model="formData.source_term" placeholder="例如: Creeper" />
        </ElFormItem>

        <ElFormItem label="目标术语" required>
          <ElInput v-model="formData.target_term" placeholder="例如: 苦力怕" />
        </ElFormItem>

        <ElFormItem label="分类">
          <ElInput v-model="formData.category" placeholder="例如: 物品、方块、生物、附魔" />
        </ElFormItem>

        <ElFormItem label="正则表达式">
          <ElSwitch v-model="formData.is_regex" />
        </ElFormItem>

        <div class="form-actions">
          <ElButton class="btn-cancel" @click="closeModal">取消</ElButton>
          <ElButton type="primary" class="btn-submit" :loading="isSubmitting" @click="handleSubmit">
            {{ editingEntry ? '保存' : '添加' }}
          </ElButton>
        </div>
      </ElForm>
    </ElDialog>

    <!-- Import Dialog -->
    <ElDialog v-model="importModalVisible" title="导入 CFPA 术语" width="520px">
      <div class="import-modal-body">
        <p class="import-desc">
          从 CFPA 官方 Minecraft 术语库导入术语数据。请将术语内容粘贴到下方文本区域。
        </p>
        <textarea
          v-model="importContent"
          class="import-textarea"
          placeholder="在此粘贴术语数据..."
          rows="10"
          :disabled="importing"
        />
        <div class="import-actions">
          <ElButton class="btn-cancel" @click="importModalVisible = false">取消</ElButton>
          <ElButton type="primary" class="btn-import-submit" :loading="importing" @click="handleImport">
            <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            {{ importing ? '导入中...' : '开始导入' }}
          </ElButton>
        </div>
      </div>
    </ElDialog>
  </div>
</template>

<style lang="scss" scoped>
.glossary-view {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px 28px 60px;
}

/* ── Page Header ────────────────────────────────── */
.page-title {
  margin: 0 0 var(--notion-spacing-xs);
  color: var(--notion-ink-deep);
}

.page-desc {
  margin: 0 0 var(--notion-spacing-xl);
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-slate);
  line-height: var(--notion-line-height-body-sm);
}

/* ── Error Alert ────────────────────────────────── */
.error-alert {
  margin-bottom: var(--notion-spacing-md);
}

/* ── Toolbar ────────────────────────────────────── */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--notion-spacing-md);
  margin-bottom: var(--notion-spacing-md);
  flex-wrap: wrap;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: var(--notion-spacing-sm);
  flex: 1;
  min-width: 0;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--notion-spacing-sm);
  flex-shrink: 0;
}

.entry-count {
  font-size: var(--notion-font-size-caption);
  color: var(--notion-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

/* ── Search Input ───────────────────────────────── */
.search-input {
  max-width: 320px;

  :deep(.el-input__wrapper) {
    background-color: var(--notion-surface);
    border: 1px solid var(--notion-hairline);
    border-radius: var(--notion-rounded-md);
    box-shadow: none;
    height: 44px;
    padding: 0 var(--notion-spacing-md);
    transition: border-color var(--notion-transition-fast);

    &:hover {
      border-color: var(--notion-hairline-strong);
    }

    &.is-focus {
      border-color: var(--notion-primary);
      box-shadow: 0 0 0 1px var(--notion-primary);
    }
  }

  :deep(.el-input__inner) {
    color: var(--notion-ink);
    font-size: var(--notion-font-size-body);

    &::placeholder {
      color: var(--notion-stone);
    }
  }

  :deep(.el-input__prefix) {
    color: var(--notion-steel);
  }
}

.search-icon {
  width: 18px;
  height: 18px;
}

/* ── Buttons ────────────────────────────────────── */
.btn-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.btn-add {
  --el-button-bg-color: var(--notion-primary);
  --el-button-border-color: var(--notion-primary);
  --el-button-hover-bg-color: var(--notion-primary-pressed);
  --el-button-hover-border-color: var(--notion-primary-pressed);
  --el-button-active-bg-color: var(--notion-primary-deep);
  --el-button-active-border-color: var(--notion-primary-deep);

  font-weight: 500;
  border-radius: var(--notion-rounded-md);
  height: auto;
  padding: 8px 18px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn-import {
  background: transparent;
  border: 1px solid var(--notion-hairline-strong);
  color: var(--notion-ink);
  font-weight: 500;
  border-radius: var(--notion-rounded-md);
  height: auto;
  padding: 8px 18px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: border-color var(--notion-transition-fast), color var(--notion-transition-fast);

  &:hover {
    border-color: var(--notion-primary);
    color: var(--notion-primary);
  }
}

/* ── Table Container ────────────────────────────── */
.table-container {
  background-color: var(--notion-canvas);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
  overflow: hidden;
  min-height: 320px;
}

.empty-state {
  padding: 80px 0;
}

/* ── Table ──────────────────────────────────────── */
.terms-table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: transparent;
  --el-table-row-hover-bg-color: var(--notion-surface-soft);

  :deep(.el-table__header-wrapper) {
    .el-table__header {
      th {
        background-color: var(--notion-surface);
        border-bottom: 1px solid var(--notion-hairline);
        color: var(--notion-slate);
        font-size: var(--notion-font-size-caption);
        font-weight: 600;
        padding: 12px var(--notion-spacing-md);
      }
    }
  }

  :deep(.el-table__body-wrapper) {
    .el-table__body {
      tr {
        border-bottom: 1px solid var(--notion-hairline-soft);

        &:last-child {
          border-bottom: none;
        }

        td {
          border-bottom: none;
          color: var(--notion-ink);
          font-size: var(--notion-font-size-caption);
          padding: 10px var(--notion-spacing-md);
        }
      }
    }
  }
}

/* ── Column Styles ──────────────────────────────── */
.col-code {
  font-family: $font-family-mono;
  font-size: var(--notion-font-size-caption);
  color: var(--notion-ink);
  background-color: var(--notion-surface);
  padding: 2px 8px;
  border-radius: var(--notion-rounded-xs);
  border: 1px solid var(--notion-hairline);
}

.col-target {
  color: var(--notion-brand-green);
  font-weight: 500;
}

.col-date {
  color: var(--notion-muted);
  font-size: var(--notion-font-size-micro);
  white-space: nowrap;
}

/* ── Tags ───────────────────────────────────────── */
.tag-category {
  background-color: var(--notion-tint-lavender);
  border-color: rgba(123, 63, 242, 0.20);
  color: var(--notion-brand-purple-800);
  font-weight: 500;
}

.tag-source {
  &.el-tag--success {
    --el-tag-bg-color: var(--notion-tint-mint);
    --el-tag-border-color: rgba(26, 174, 57, 0.20);
    --el-tag-text-color: var(--notion-brand-green);
  }

  &:not(.el-tag--success) {
    --el-tag-bg-color: var(--notion-tint-lavender);
    --el-tag-border-color: rgba(123, 63, 242, 0.20);
    --el-tag-text-color: var(--notion-brand-purple-800);
  }
}

.tag-regex {
  &.el-tag--success {
    --el-tag-bg-color: var(--notion-tint-mint);
    --el-tag-border-color: rgba(26, 174, 57, 0.20);
    --el-tag-text-color: var(--notion-brand-green);
  }

  &.el-tag--info {
    --el-tag-bg-color: transparent;
    --el-tag-border-color: transparent;
    --el-tag-text-color: var(--notion-muted);
  }
}

/* ── Action Cell ────────────────────────────────── */
.action-cell {
  display: flex;
  align-items: center;
  gap: 2px;
}

.btn-action {
  --el-button-text-color: var(--notion-muted);
  --el-button-hover-text-color: var(--notion-ink);
  --el-button-active-text-color: var(--notion-ink);

  padding: 4px;

  &.el-button--danger {
    --el-button-hover-text-color: var(--notion-semantic-error);
    --el-button-active-text-color: var(--notion-semantic-error);
  }
}

.action-icon {
  width: 16px;
  height: 16px;
}

/* ── Entry Form ─────────────────────────────────── */
.entry-form {
  :deep(.el-form-item__label) {
    color: var(--notion-charcoal);
    font-weight: 500;
  }

  :deep(.el-input__wrapper) {
    background-color: var(--notion-canvas);
    border: 1px solid var(--notion-hairline-strong);
    border-radius: var(--notion-rounded-md);
    box-shadow: none;
    transition: border-color var(--notion-transition-fast);

    &:hover {
      border-color: var(--notion-steel);
    }

    &.is-focus {
      border-color: var(--notion-primary);
      box-shadow: 0 0 0 1px var(--notion-primary);
    }
  }

  :deep(.el-switch.is-checked .el-switch__core) {
    border-color: var(--notion-primary);
    background-color: var(--notion-primary);
  }
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--notion-spacing-sm);
  margin-top: var(--notion-spacing-xl);
}

.btn-cancel {
  background: transparent;
  border: 1px solid var(--notion-hairline-strong);
  color: var(--notion-ink);
  font-weight: 500;
  border-radius: var(--notion-rounded-md);
  height: auto;
  padding: 8px 18px;

  &:hover {
    border-color: var(--notion-steel);
  }
}

.btn-submit {
  --el-button-bg-color: var(--notion-primary);
  --el-button-border-color: var(--notion-primary);
  --el-button-hover-bg-color: var(--notion-primary-pressed);
  --el-button-hover-border-color: var(--notion-primary-pressed);
  --el-button-active-bg-color: var(--notion-primary-deep);
  --el-button-active-border-color: var(--notion-primary-deep);

  font-weight: 500;
  border-radius: var(--notion-rounded-md);
  height: auto;
  padding: 8px 18px;
}

/* ── Import Dialog ──────────────────────────────── */
.import-modal-body {
  position: relative;
}

.import-desc {
  margin: 0 0 var(--notion-spacing-md);
  font-size: var(--notion-font-size-caption);
  color: var(--notion-slate);
  line-height: var(--notion-line-height-body-sm);
}

.import-textarea {
  width: 100%;
  min-height: 180px;
  background-color: var(--notion-canvas);
  border: 1px solid var(--notion-hairline-strong);
  border-radius: var(--notion-rounded-md);
  color: var(--notion-ink);
  font-family: $font-family-mono;
  font-size: var(--notion-font-size-caption);
  padding: var(--notion-spacing-sm);
  resize: vertical;
  outline: none;
  transition: border-color var(--notion-transition-fast);

  &::placeholder {
    color: var(--notion-stone);
  }

  &:focus {
    border-color: var(--notion-primary);
    box-shadow: 0 0 0 1px var(--notion-primary);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.import-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--notion-spacing-sm);
  margin-top: var(--notion-spacing-md);
}

.btn-import-submit {
  --el-button-bg-color: var(--notion-primary);
  --el-button-border-color: var(--notion-primary);
  --el-button-hover-bg-color: var(--notion-primary-pressed);
  --el-button-hover-border-color: var(--notion-primary-pressed);
  --el-button-active-bg-color: var(--notion-primary-deep);
  --el-button-active-border-color: var(--notion-primary-deep);

  font-weight: 500;
  border-radius: var(--notion-rounded-md);
  height: auto;
  padding: 8px 18px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

/* ── Text Muted ─────────────────────────────────── */
.text-muted {
  color: var(--notion-muted);
}
</style>
