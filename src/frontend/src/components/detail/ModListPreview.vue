<script setup>
import { computed, ref, watch } from 'vue'
import { ElTable, ElTableColumn, ElEmpty, ElTooltip, ElPagination } from 'element-plus'
import { useModpackStore } from '@/stores/modpack'

const modpackStore = useModpackStore()

function formatFileSize(bytes) {
  if (bytes == null || bytes === 0) return '---'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

const modFiles = computed(() => modpackStore.versionDetail?.mods || [])

const dataSource = computed(() => {
  return modFiles.value.map((mod, index) => ({
    ...mod,
    _key: mod.mod_external_id || index
  }))
})

const modCount = computed(() => dataSource.value.length)

const hasSelectedVersion = computed(() => !!modpackStore.selectedVersion)

const tableLoading = computed(() => modpackStore.versionDetailLoading)

const currentPage = ref(1)
const pageSize = ref(20)

watch(() => modpackStore.selectedVersion, () => {
  currentPage.value = 1
})

const paginatedMods = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return dataSource.value.slice(start, start + pageSize.value)
})
</script>

<template>
  <div class="mod-list-card">
    <h3 class="card-title">Mod 清单</h3>

    <ElEmpty
      v-if="!hasSelectedVersion && !tableLoading"
      description="请先选择版本"
    />

    <ElEmpty
      v-else-if="hasSelectedVersion && !tableLoading && modCount === 0"
      description="该版本无 Mod 文件"
    />

    <template v-else>
      <div v-if="!tableLoading" class="mod-stats">
        共 {{ modCount }} 个 Mod 文件
      </div>

      <ElTable
        v-loading="tableLoading"
        :data="paginatedMods"
        row-key="_key"
        class="mod-table"
      >
        <ElTableColumn
          prop="name"
          label="文件名"
          :show-overflow-tooltip="true"
          min-width="300"
        />
        <ElTableColumn label="文件大小" width="120" align="right">
          <template #default="{ row }">
            {{ formatFileSize(row.file_size) }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="哈希值" width="160">
          <template #default="{ row }">
            <ElTooltip
              :content="row.mod_external_id || '---'"
              placement="top"
            >
              <span class="hash-cell">
                {{ row.mod_external_id ? row.mod_external_id.substring(0, 8) + '...' : '---' }}
              </span>
            </ElTooltip>
          </template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="100" align="center">
          <template #default="{ row }">
            <a
              v-if="row.download_url"
              :href="row.download_url"
              target="_blank"
              rel="noopener"
              class="download-link"
            >
              下载
            </a>
            <span v-else class="no-link">---</span>
          </template>
        </ElTableColumn>
      </ElTable>

      <ElPagination
        v-if="modCount > pageSize"
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="modCount"
        layout="prev, pager, next"
        class="mod-pagination"
      />
    </template>
  </div>
</template>

<style lang="scss" scoped>
.mod-list-card {
  background: var(--notion-canvas);
  border-radius: var(--notion-rounded-lg);
  border: 1px solid var(--notion-hairline);
  padding: var(--notion-spacing-xl);
}

.card-title {
  font-size: var(--notion-font-size-h5);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0 0 var(--notion-spacing-md) 0;
}

.mod-stats {
  margin-bottom: var(--notion-spacing-sm);
  color: var(--notion-slate);
  font-size: var(--notion-font-size-body-sm);
}

.hash-cell {
  font-family: monospace;
  font-size: var(--notion-font-size-micro);
  color: var(--notion-steel);
  cursor: default;
  user-select: all;
}

.download-link {
  color: var(--notion-link-blue);
  text-decoration: none;

  &:hover {
    text-decoration: underline;
  }
}

.no-link {
  color: var(--notion-muted);
}

.mod-pagination {
  margin-top: var(--notion-spacing-md);
  display: flex;
  justify-content: center;
}

:deep(.mod-table) {
  --el-table-header-bg-color: var(--notion-surface);
  --el-table-header-text-color: var(--notion-slate);
  --el-table-tr-bg-color: var(--notion-canvas);
  --el-table-row-hover-bg-color: var(--notion-surface-soft);
  --el-table-border-color: var(--notion-hairline-soft);
  background: var(--notion-canvas);

  .el-table__header th {
    font-size: var(--notion-font-size-micro);
    font-weight: 600;
    text-transform: uppercase;
  }

  .el-table__body tr td {
    color: var(--notion-charcoal);
    font-size: var(--notion-font-size-body-sm);
  }
}

:deep(.mod-pagination) {
  --el-pagination-bg-color: transparent;
  --el-pagination-button-bg-color: transparent;
  --el-pagination-text-color: var(--notion-steel);
  --el-pagination-hover-color: var(--notion-ink);
  --el-pagination-button-disabled-bg-color: transparent;
}

:deep(.el-empty) {
  padding: var(--notion-spacing-xxl) 0;

  .el-empty__description {
    color: var(--notion-muted);
  }
}

:deep(.el-loading-mask) {
  background-color: rgba(255, 255, 255, 0.6);
}

@media (max-width: 576px) {
  .mod-list-card {
    padding: var(--notion-spacing-md);
  }
}
</style>
