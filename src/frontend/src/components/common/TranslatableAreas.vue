<script setup>
import { ElCheckbox, ElTag } from 'element-plus'
import { useLocalPackStore } from '@/stores/localPack'
import { getAreaMeta, getTargetStrategyLabel, getItemTargetPath } from '@/utils/localizationDelivery'

const localPackStore = useLocalPackStore()

function getItemCount(area) {
  return area.items ? area.items.length : area.count || 0
}

function getEntryCount(area) {
  if (!area.items) return area.count || 0
  return area.items.reduce((sum, item) => sum + (item.entry_count || 0), 0)
}

function getAreaLabel(area) {
  return area.label || getAreaMeta(area.type).label || area.type
}

function getAreaDescription(area) {
  return getAreaMeta(area.type).description
}

function getAreaColor(area) {
  return getAreaMeta(area.type).color || ''
}

function formatTargetStrategy(item) {
  if (!item?.target_strategy) return '目标策略待后端提供'
  return getTargetStrategyLabel(item.target_strategy)
}

function formatTargetPath(item) {
  return getItemTargetPath(item) || '—'
}
</script>

<template>
  <div class="translatable-areas">
    <div class="areas-header">
      <h3 class="areas-title">待翻译区域</h3>
      <span class="areas-count">{{ localPackStore.selectableAreas.length }} 个区域</span>
    </div>

    <div v-if="localPackStore.selectableAreas.length === 0" class="areas-empty">
      未检测到待翻译内容
    </div>

    <div class="areas-grid">
      <div
        v-for="area in localPackStore.selectableAreas"
        :key="area.type"
        class="area-card"
        :class="{ 'area-card--selected': localPackStore.selectedAreas.includes(area.type) }"
        @click="localPackStore.toggleArea(area.type)"
      >
        <div class="area-card-header">
          <ElCheckbox
            :model-value="localPackStore.selectedAreas.includes(area.type)"
            @click.stop
            @change="localPackStore.toggleArea(area.type)"
          />
          <span class="area-card-label">{{ getAreaLabel(area) }}</span>
          <ElTag :type="getAreaColor(area)" size="small">
            {{ getItemCount(area) }} 文件
          </ElTag>
        </div>

        <p class="area-card-desc">{{ getAreaDescription(area) }}</p>

        <div class="area-card-body">
          <div class="area-stat">
            <span class="area-stat-label">条目数</span>
            <span class="area-stat-value">{{ getEntryCount(area) }}</span>
          </div>
          <div class="area-stat">
            <span class="area-stat-label">文件数</span>
            <span class="area-stat-value">{{ getItemCount(area) }}</span>
          </div>
        </div>

        <ul class="area-items" v-if="area.items && area.items.length > 0 && area.items.length <= 5">
          <li
            v-for="(item, idx) in area.items"
            :key="idx"
            class="area-items-entry"
          >
            <div class="area-item-main">
              <span class="area-items-file">{{ item.file || item.mod_name || '-' }}</span>
              <span class="area-item-target">{{ formatTargetStrategy(item) }}</span>
              <span class="area-item-path" :title="formatTargetPath(item)">{{ formatTargetPath(item) }}</span>
            </div>
            <span class="area-items-count">{{ item.entry_count || 0 }} 条</span>
          </li>
        </ul>
        <p class="area-items-more" v-else-if="area.items && area.items.length > 5">
          等 {{ area.items.length }} 个文件
        </p>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.translatable-areas {
  margin-bottom: var(--notion-spacing-md);
}

.areas-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--notion-spacing-md);
}

.areas-title {
  font-size: var(--notion-font-size-h5);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0;
}

.areas-count {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-steel);
  background: var(--notion-surface);
  padding: 2px 8px;
  border-radius: var(--notion-rounded-sm);
}

.areas-empty {
  padding: var(--notion-spacing-xxl);
  text-align: center;
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-steel);
  background: var(--notion-surface);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-md);
}

.areas-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--notion-spacing-md);
}

.area-card {
  background: var(--notion-canvas);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-md);
  padding: var(--notion-spacing-md);
  cursor: pointer;
  transition: border-color var(--notion-transition-fast), box-shadow var(--notion-transition-fast);

  &:hover {
    border-color: var(--notion-primary);
    box-shadow: 0 0 0 1px var(--notion-primary);
  }
}

.area-card--selected {
  border-color: var(--notion-primary);
  background: var(--notion-tint-lavender);
}

.area-card-header {
  display: flex;
  align-items: center;
  gap: var(--notion-spacing-xs);
  margin-bottom: var(--notion-spacing-xs);
}

.area-card-label {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 600;
  color: var(--notion-ink);
  flex: 1;
}

.area-card-desc {
  margin: 0 0 var(--notion-spacing-sm);
  font-size: var(--notion-font-size-micro);
  line-height: var(--notion-line-height-caption);
  color: var(--notion-steel);
}

.area-card-body {
  display: flex;
  gap: var(--notion-spacing-xl);
  margin-bottom: var(--notion-spacing-xs);
}

.area-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.area-stat-label {
  font-size: var(--notion-font-size-micro);
  color: var(--notion-stone);
}

.area-stat-value {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 600;
  color: var(--notion-ink);
}

.area-items {
  list-style: none;
  padding: 0;
  margin: var(--notion-spacing-sm) 0 0;
  border-top: 1px solid var(--notion-hairline);
  padding-top: var(--notion-spacing-sm);
}

.area-items-entry {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--notion-spacing-sm);
  padding: 4px 0;
  font-size: var(--notion-font-size-micro);
}

.area-item-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.area-items-file {
  color: var(--notion-charcoal);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.area-item-target {
  color: var(--notion-ink);
}

.area-item-path {
  color: var(--notion-steel);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.area-items-count {
  color: var(--notion-steel);
  flex-shrink: 0;
}

.area-items-more {
  margin: var(--notion-spacing-sm) 0 0;
  font-size: var(--notion-font-size-micro);
  color: var(--notion-muted);
  text-align: center;
}
</style>
