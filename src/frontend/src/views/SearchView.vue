<script setup>
import { ElInput, ElButton, ElEmpty, ElAlert, ElBacktop } from 'element-plus'
import { useSearchStore } from '@/stores/search'
import SearchFilterBar from '@/components/search/SearchFilterBar.vue'
import SearchResultList from '@/components/search/SearchResultList.vue'
import { onMounted, computed } from 'vue'

const searchStore = useSearchStore()

const resultSummary = computed(() => {
  if (searchStore.loading) return '正在从多个来源获取整合包结果。'
  if (searchStore.error) return '搜索出现问题，请检查关键词或稍后重试。'
  if (searchStore.hasResults) return `共找到 ${searchStore.results.length} 个整合包候选。`
  if (searchStore.searched) return '未找到匹配项，可尝试调整筛选条件。'
  return '输入关键词后可直接在工作区内浏览可本地化整合包。'
})

function onSearch() {
  searchStore.doSearch()
}

function onLoadMore() {
  searchStore.loadMore()
}

onMounted(() => {
  onSearch()
})
</script>

<template>
  <div class="search-view">
    <section class="search-hero">
      <div class="search-hero-copy">
        <div class="search-kicker-row">
          <span class="search-kicker">在线检索</span>
          <span class="dev-badge" title="该功能尚在开发中，部分能力可能尚未完成">
            <span class="dev-badge-dot" aria-hidden="true"></span>
            此功能尚在开发中
          </span>
        </div>
        <h2 class="search-title">翻译补丁检索</h2>
        <p class="search-subtitle">请选择正确的整合包与游戏版本</p>
      </div>
      <div class="search-summary-card">
        <span class="summary-label">当前状态</span>
        <span class="summary-value">{{ resultSummary }}</span>
      </div>
    </section>

    <section class="search-command-panel">
      <div class="search-input-row">
        <el-input
          v-model="searchStore.query"
          size="large"
          placeholder="搜索 Minecraft 整合包..."
          clearable
          @keyup.enter="onSearch"
        />
        <el-button type="primary" size="large" @click="onSearch">
          搜索
        </el-button>
      </div>
      <SearchFilterBar />
    </section>

    <section
      v-loading="searchStore.loading"
      element-loading-text="搜索中..."
      class="results-area"
    >
      <el-empty
        v-if="!searchStore.searched && !searchStore.loading"
        description="输入关键词开始搜索"
      />

      <el-empty
        v-else-if="searchStore.isEmpty"
        description="没有找到相关整合包，请尝试其他关键词"
      />

      <el-alert
        v-else-if="searchStore.error"
        :title="searchStore.error"
        type="error"
        show-icon
        :closable="false"
        class="error-alert"
      />

      <template v-if="searchStore.hasResults">
        <SearchResultList />
        <div v-if="searchStore.hasMore" class="load-more-container">
          <el-button
            :loading="searchStore.loadingMore"
            @click="onLoadMore"
            class="load-more-btn"
          >
            加载更多
          </el-button>
        </div>
        <div v-else-if="searchStore.results.length > 0" class="all-loaded">
          已加载全部结果
        </div>
      </template>
    </section>

    <el-backtop />
  </div>
</template>

<style lang="scss" scoped>
.search-view {
  padding: $spacing-xl;
  max-width: $container-max;
  margin: 0 auto;
}

.search-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: $spacing-lg;
  align-items: stretch;
  margin-bottom: $spacing-lg;

  @media (max-width: 960px) {
    grid-template-columns: 1fr;
  }
}

.search-hero-copy,
.search-summary-card,
.search-command-panel,
.results-area {
  background: var(--fluent-surface-2);
  border: 1px solid var(--notion-hairline-soft);
  box-shadow: var(--notion-shadow-subtle);
}

.search-hero-copy {
  border-radius: $rounded-xl;
  padding: $spacing-xl;
  display: flex;
  flex-direction: column;
  gap: $spacing-xs;
}

.search-kicker {
  font-size: $font-size-micro-uppercase;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--fluent-accent);
  font-weight: $font-weight-semibold;
}

.search-kicker-row {
  display: inline-flex;
  align-items: center;
  gap: $spacing-sm;
  flex-wrap: wrap;
}

.dev-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: $font-size-caption;
  line-height: 1.4;
  font-weight: $font-weight-semibold;
  color: $color-warning;
  background: rgba($color-warning, 0.14);
  border: 1px solid rgba($color-warning, 0.45);
  white-space: nowrap;
  user-select: none;
}

.dev-badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: $color-warning;
  box-shadow: 0 0 0 3px rgba($color-warning, 0.18);
  flex-shrink: 0;
}

.search-title {
  margin: 0;
  font-size: $font-size-h3;
  line-height: $line-height-h3;
  color: var(--notion-ink);
}

.search-subtitle {
  margin: 0;
  max-width: 720px;
  font-size: $font-size-body-sm;
  line-height: $line-height-body-sm;
  color: var(--notion-steel);
}

.search-summary-card {
  border-radius: $rounded-xl;
  padding: $spacing-lg;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  background: linear-gradient(180deg, var(--fluent-surface-3), var(--fluent-surface-2));
}

.summary-label {
  font-size: $font-size-caption;
  color: var(--notion-steel);
}

.summary-value {
  font-size: $font-size-body-sm;
  line-height: $line-height-body-sm;
  color: var(--notion-ink);
  font-weight: $font-weight-medium;
}

.search-command-panel {
  border-radius: $rounded-xl;
  padding: $spacing-lg;
  margin-bottom: $spacing-lg;
}

.search-input-row {
  display: flex;
  gap: $spacing-sm;
  width: 100%;
  margin-bottom: $spacing-sm;

  :deep(.el-input) {
    flex: 1;
  }

  :deep(.el-input__wrapper) {
    min-height: 40px;
    padding: 0 $spacing-sm;
    background: var(--fluent-control-bg);
    border: 1px solid var(--fluent-control-border);
    border-radius: $rounded-md;
    box-shadow: none;

    &:hover {
      border-color: var(--fluent-control-border-hover);
    }

    &.is-focus {
      border-color: var(--fluent-control-border-active);
      box-shadow: var(--fluent-focus-ring);
    }
  }

  :deep(.el-input__inner) {
    color: var(--notion-ink);

    &::placeholder {
      color: var(--notion-muted);
    }
  }

  :deep(.el-button--primary) {
    min-width: 108px;
    border-radius: $rounded-sm;
    box-shadow: none;
  }

  @media (max-width: 640px) {
    flex-direction: column;

    :deep(.el-button) {
      width: 100%;
    }
  }
}

.results-area {
  min-height: 320px;
  border-radius: $rounded-xl;
  padding: $spacing-lg;

  :deep(.el-empty) {
    padding: 56px 0;
  }

  :deep(.el-empty__description p) {
    color: var(--notion-muted);
  }
}

.error-alert {
  :deep(.el-alert) {
    background-color: var(--fluent-surface-danger-subtle);
    border: 1px solid rgba($color-error, 0.28);
    border-radius: $rounded-md;
  }

  :deep(.el-alert__title) {
    color: var(--notion-ink);
  }
}

.load-more-container {
  margin-top: $spacing-xl;
  display: flex;
  justify-content: center;

  .load-more-btn {
    min-width: 132px;
    font-weight: $font-weight-semibold;
  }
}

.all-loaded {
  text-align: center;
  margin-top: $spacing-xl;
  color: var(--notion-steel);
  font-size: $font-size-body-sm;
}

:deep(.el-backtop) {
  background-color: var(--fluent-surface-3);
  border: 1px solid var(--notion-hairline);
  color: var(--notion-steel);
  border-radius: $rounded-md;
  box-shadow: var(--notion-shadow-subtle);

  &:hover {
    background-color: var(--fluent-control-bg-hover);
    color: var(--notion-ink);
  }
}
</style>
