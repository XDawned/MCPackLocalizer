<script setup>
import { computed } from 'vue'
import { ElSelect, ElOption, ElEmpty } from 'element-plus'
import { useModpackStore } from '@/stores/modpack'

const modpackStore = useModpackStore()

function formatVersionOption(version) {
  const vn = version.version_number || '未知版本'
  const mcLabel = version.mc_version
    || (version.game_versions?.length ? version.game_versions.join('/') : '')
  const mcPart = mcLabel ? ` (${mcLabel})` : ''
  return `${vn}${mcPart}`
}

const selectedVersionId = computed({
  get: () => modpackStore.selectedVersion,
  set: (val) => {
    if (val) {
      modpackStore.loadVersionDetail(val)
    }
  }
})

const isLoading = computed(() =>
  modpackStore.versionsLoading || modpackStore.versionDetailLoading
)

const versionOptionList = computed(() =>
  modpackStore.versions.map(ver => ({
    value: ver.id,
    label: formatVersionOption(ver)
  }))
)
</script>

<template>
  <div class="version-selector-card">
    <h3 class="card-title">选择版本</h3>

    <ElEmpty
      v-if="!modpackStore.versionsLoading && modpackStore.versions.length === 0"
      description="暂无可用版本"
    />

    <ElSelect
      v-else
      v-model="selectedVersionId"
      :loading="isLoading"
      placeholder="请选择版本"
      class="version-select"
    >
      <ElOption
        v-for="item in versionOptionList"
        :key="item.value"
        :label="item.label"
        :value="item.value"
      />
    </ElSelect>
  </div>
</template>

<style lang="scss" scoped>
.version-selector-card {
  background: var(--notion-canvas);
  border-radius: var(--notion-rounded-lg);
  border: 1px solid var(--notion-hairline);
  padding: var(--notion-spacing-xl);
  margin-bottom: var(--notion-spacing-xl);
  transition: border-color var(--notion-transition-normal), box-shadow var(--notion-transition-normal);

  &:hover {
    border-color: var(--notion-hairline-strong);
    box-shadow: var(--notion-shadow-card);
  }
}

.card-title {
  font-size: var(--notion-font-size-h5);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0 0 var(--notion-spacing-md) 0;
}

.version-select {
  width: 100%;
  max-width: 500px;

  :deep(.el-select__wrapper) {
    background: var(--notion-canvas);
    border: 1px solid var(--notion-hairline-strong);
    border-radius: var(--notion-rounded-md);
    box-shadow: none;
    padding: var(--notion-spacing-sm) var(--notion-spacing-md);
    min-height: 44px;
    transition: border-color var(--notion-transition-fast), box-shadow var(--notion-transition-fast);

    &:hover {
      border-color: var(--notion-steel);
    }

    &.is-focus {
      border-color: var(--notion-primary);
      box-shadow: 0 0 0 2px rgba(86, 69, 212, 0.12);
    }
  }

  :deep(.el-select__placeholder) {
    color: var(--notion-muted);
  }

  :deep(.el-select__selected-item) {
    color: var(--notion-ink);
    font-size: var(--notion-font-size-body);
  }

  :deep(.el-select__caret) {
    color: var(--notion-steel);
  }

  :deep(.el-select__loading) {
    color: var(--notion-primary);
  }
}
</style>

<style lang="scss">
.version-selector-card .version-select {
  .el-select-dropdown__item {
    color: var(--notion-ink);
    font-size: var(--notion-font-size-body);

    &.is-selected {
      color: var(--notion-primary);
      font-weight: 500;
    }

    &.is-hovering {
      background: var(--notion-surface);
    }
  }

  .el-select-dropdown__list {
    padding: var(--notion-spacing-xs);
  }

  .el-popper.is-light {
    background: var(--notion-canvas);
    border: 1px solid var(--notion-hairline);
    border-radius: var(--notion-rounded-md);
    box-shadow: var(--notion-shadow-modal);
  }
}
</style>
