<script setup>
import { ElEmpty } from 'element-plus'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = route.meta?.title || '功能开发中'
</script>

<template>
  <div class="placeholder-view">
    <div class="coming-soon-card">
      <ElEmpty
        :description="title"
      />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.placeholder-view {
  max-width: 900px;
  margin: 0 auto;
  padding: 80px 24px;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100%;
}

.coming-soon-card {
  border: 2px dashed var(--notion-hairline-strong);
  border-radius: var(--notion-rounded-lg);
  padding: 48px 64px;
  background: transparent;

  :deep(.el-empty) {
    padding: 0;
  }

  :deep(.el-empty__image) {
    width: 100px;
    height: 100px;
    margin-bottom: var(--notion-spacing-sm);
  }

  :deep(.el-empty__description) {
    margin-top: 0;
    color: var(--notion-slate);
    font-size: var(--notion-font-size-body);
    line-height: var(--notion-line-height-body);
    font-weight: 500;
  }
}
</style>
