<script setup>
import { useSearchStore } from '@/stores/search'
import ModpackCard from './ModpackCard.vue'

const searchStore = useSearchStore()
</script>

<template>
  <div class="result-list">
    <div class="result-header">
      <span class="result-count">
        已加载 <strong>{{ searchStore.results.length }}</strong> 个整合包
      </span>
    </div>

    <div
      v-if="!searchStore.hasMore && searchStore.results.length > 0 && searchStore.total > 0"
      class="all-loaded-banner"
    >
      已展示全部 {{ searchStore.total }} 个结果
    </div>

    <div class="result-cards">
      <ModpackCard
        v-for="item in searchStore.results"
        :key="item.platform + '/' + item.id"
        :item="item"
      />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.result-list {
  width: 100%;
  font-family: var(--notion-font-sans);
}

.result-header {
  display: flex;
  align-items: baseline;
  gap: 16px;
  margin-bottom: var(--notion-spacing-sm);
  padding: var(--notion-spacing-xs) 0;
}

.result-count {
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-steel);

  strong {
    color: var(--notion-primary);
    font-weight: 600;
  }
}

.result-progress {
  font-size: var(--notion-font-size-caption);
  color: var(--notion-muted);
}

.all-loaded-banner {
  text-align: center;
  margin-bottom: var(--notion-spacing-md);
  padding: var(--notion-spacing-xs) 0;
  color: var(--notion-primary);
  font-size: var(--notion-font-size-body-sm);
  border-bottom: 1px solid var(--notion-hairline);
}

.result-cards {
  display: flex;
  flex-direction: column;
  gap: var(--notion-spacing-sm);
}
</style>
