<script setup>
import { computed } from 'vue'
import { ElSelect, ElOption, ElButton } from 'element-plus'
import { useSearchStore } from '@/stores/search'

const searchStore = useSearchStore()

const selectedSources = computed({
  get: () => searchStore.sources,
  set: (val) => {
    searchStore.sources = val.length > 0 ? val : ['curseforge', 'modrinth']
    if (searchStore.query) searchStore.doSearch()
  }
})

const selectedCategory = computed({
  get: () => searchStore.category,
  set: (val) => {
    searchStore.category = val || null
    if (searchStore.query) searchStore.doSearch()
  }
})

const selectedLoader = computed({
  get: () => searchStore.modLoader,
  set: (val) => {
    searchStore.modLoader = val || null
    if (searchStore.query) searchStore.doSearch()
  }
})

const selectedVersion = computed({
  get: () => searchStore.gameVersion,
  set: (val) => {
    searchStore.gameVersion = val || null
    if (searchStore.query) searchStore.doSearch()
  }
})

function onReset() {
  searchStore.resetFilters()
}
</script>

<template>
  <div class="filter-bar">
    <div class="filter-bar-header">
      <div class="filter-header-copy">
        <span class="filter-kicker">筛选条件</span>
        <span class="filter-description">组合来源、分类、加载器与版本，缩小结果范围。</span>
      </div>
      <ElButton text @click="onReset" :disabled="searchStore.loading" class="reset-btn">
        重置筛选
      </ElButton>
    </div>

    <div class="filter-grid">
      <div class="filter-item filter-item--wide">
        <span class="filter-label">搜索源</span>
        <ElSelect
          v-model="selectedSources"
          multiple
          placeholder="选择来源"
          :disabled="searchStore.loading"
          collapse-tags
          collapse-tags-tooltip
        >
          <ElOption
            v-for="item in searchStore.availableSources"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </ElSelect>
      </div>

      <div class="filter-item">
        <span class="filter-label">分类</span>
        <ElSelect
          v-model="selectedCategory"
          placeholder="不限"
          clearable
          filterable
          :disabled="searchStore.loading"
        >
          <ElOption
            v-for="item in searchStore.categories"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </ElSelect>
      </div>

      <div class="filter-item">
        <span class="filter-label">加载器</span>
        <ElSelect
          v-model="selectedLoader"
          placeholder="不限"
          clearable
          filterable
          :disabled="searchStore.loading"
        >
          <ElOption
            v-for="item in searchStore.loaders"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </ElSelect>
      </div>

      <div class="filter-item">
        <span class="filter-label">MC 版本</span>
        <ElSelect
          v-model="selectedVersion"
          placeholder="不限"
          clearable
          filterable
          :disabled="searchStore.loading"
        >
          <ElOption
            v-for="item in searchStore.gameVersions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </ElSelect>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.filter-bar {
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
}

.filter-bar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $spacing-sm;

  @media (max-width: 640px) {
    flex-direction: column;
    align-items: flex-start;
  }
}

.filter-header-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.filter-kicker {
  font-size: $font-size-caption;
  font-weight: $font-weight-semibold;
  color: var(--notion-ink);
}

.filter-description {
  font-size: $font-size-caption;
  color: var(--notion-steel);
}

.filter-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: $spacing-sm;

  @media (max-width: 1040px) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  @media (max-width: 640px) {
    grid-template-columns: 1fr;
  }
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filter-item--wide {
  @media (min-width: 1041px) {
    grid-column: span 2;
  }
}

.filter-label {
  font-size: var(--notion-font-size-caption);
  color: var(--notion-steel);
  white-space: nowrap;
  flex-shrink: 0;
}

:deep(.el-select) {
  width: 100%;
  --el-select-border-color-hover: var(--fluent-control-border-hover);
  --el-select-input-focus-border-color: var(--fluent-control-border-active);

  .el-select__wrapper {
    background: var(--fluent-control-bg);
    border: 1px solid var(--fluent-control-border);
    border-radius: var(--notion-rounded-md);
    box-shadow: none;
    padding: 4px var(--notion-spacing-sm);
    min-height: 36px;
    transition: border-color 150ms ease, box-shadow 150ms ease, background-color 150ms ease;

    &:hover {
      border-color: var(--fluent-control-border-hover);
      background: var(--fluent-control-bg-hover);
    }

    &.is-focus,
    &.is-focused {
      border-color: var(--fluent-control-border-active);
      box-shadow: var(--fluent-focus-ring);
    }
  }

  .el-select__placeholder {
    color: var(--notion-muted);
  }

  .el-select__selected-item {
    color: var(--notion-ink);
    font-size: var(--notion-font-size-caption);
  }

  .el-select__caret {
    color: var(--notion-steel);
  }

  .el-select__tags {
    gap: 4px;

    .el-tag {
      background: var(--fluent-surface-accent-subtle);
      border-color: var(--notion-hairline-soft);
      color: var(--notion-ink);
      border-radius: var(--notion-rounded-sm);
      font-size: var(--notion-font-size-micro);

      .el-tag__close {
        color: var(--notion-steel);

        &:hover {
          background: var(--notion-hairline-soft);
          color: var(--notion-ink);
        }
      }
    }
  }

  .el-select__tags-text {
    color: var(--notion-ink);
  }

  .el-select__input-wrapper {
    .el-select__input {
      color: var(--notion-ink);

      &::placeholder {
        color: var(--notion-muted);
      }
    }
  }
}

:deep(.el-select-dropdown__item) {
  &.is-selected {
    color: var(--fluent-accent);
    font-weight: $font-weight-medium;
  }

  &.is-hovering {
    background: var(--fluent-surface-accent-subtle);
  }
}

.reset-btn {
  color: var(--notion-steel);
  font-size: var(--notion-font-size-caption);
  padding: 4px var(--notion-spacing-sm);
  border-radius: var(--notion-rounded-sm);
  transition: color 150ms ease, background 150ms ease;
  height: auto;
  min-height: unset;

  &:hover {
    color: var(--notion-ink);
    background: var(--fluent-surface-accent-subtle);
  }

  &:disabled {
    color: var(--notion-muted);
    background: transparent;
  }
}
</style>
