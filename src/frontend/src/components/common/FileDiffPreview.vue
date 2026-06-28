<script setup>
import { ElEmpty } from 'element-plus'
import { vLoading } from 'element-plus'

const props = defineProps({
  addedFiles: { type: Array, default: () => [] },
  modifiedFiles: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false }
})

function formatSize(bytes) {
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB'
  if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return bytes + ' B'
}
</script>

<template>
  <div
    class="diff-preview"
    v-loading="loading"
  >
    <ElEmpty
      v-if="!loading && addedFiles.length === 0 && modifiedFiles.length === 0"
      description="暂无文件变更"
    />

    <template v-else-if="!loading">
      <div v-if="addedFiles.length > 0" class="diff-section">
        <div class="diff-section-header">
          <span class="diff-dot diff-dot--green" />
          <span class="diff-section-title">新增文件 ({{ addedFiles.length }})</span>
        </div>
        <div class="diff-list">
          <div
            v-for="file in addedFiles"
            :key="file.path"
            class="diff-item"
          >
            <span class="diff-item-path">{{ file.path }}</span>
            <span class="diff-item-size diff-item-size--green">{{ formatSize(file.size) }}</span>
          </div>
        </div>
      </div>

      <div v-if="modifiedFiles.length > 0" class="diff-section">
        <div class="diff-section-header">
          <span class="diff-dot diff-dot--orange" />
          <span class="diff-section-title">修改文件 ({{ modifiedFiles.length }})</span>
        </div>
        <div class="diff-list">
          <div
            v-for="file in modifiedFiles"
            :key="file.path"
            class="diff-item"
          >
            <span class="diff-item-path">{{ file.path }}</span>
            <span class="diff-item-size diff-item-size--orange">
              {{ formatSize(file.original_size) }} → {{ formatSize(file.new_size) }}
            </span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.diff-preview {
  background: var(--notion-canvas);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
  padding: var(--notion-spacing-md);
}

.diff-section {
  & + & {
    margin-top: var(--notion-spacing-md);
    padding-top: var(--notion-spacing-md);
    border-top: 1px solid var(--notion-hairline);
  }
}

.diff-section-header {
  display: flex;
  align-items: center;
  gap: var(--notion-spacing-xs);
  margin-bottom: var(--notion-spacing-xs);
}

.diff-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--notion-rounded-full);
  flex-shrink: 0;

  &--green {
    background: var(--notion-brand-green);
    box-shadow: 0 0 6px rgba(26, 174, 57, 0.4);
  }

  &--orange {
    background: var(--notion-brand-orange);
    box-shadow: 0 0 6px rgba(221, 91, 0, 0.4);
  }
}

.diff-section-title {
  font-family: var(--notion-font-sans);
  font-size: var(--notion-font-size-caption);
  font-weight: 600;
  color: var(--notion-ink);
}

.diff-list {
  display: flex;
  flex-direction: column;
  gap: var(--notion-spacing-xxs);
}

.diff-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--notion-spacing-xxs) var(--notion-spacing-sm);
  background: var(--notion-surface);
  border-radius: var(--notion-rounded-sm);
  gap: var(--notion-spacing-sm);
  min-width: 0;
}

.diff-item-path {
  font-family: var(--notion-font-mono);
  font-size: var(--notion-font-size-micro);
  color: var(--notion-slate);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.diff-item-size {
  font-family: var(--notion-font-mono);
  font-size: var(--notion-font-size-micro-uppercase);
  flex-shrink: 0;

  &--green {
    color: var(--notion-brand-green);
  }

  &--orange {
    color: var(--notion-brand-orange);
  }
}
</style>
