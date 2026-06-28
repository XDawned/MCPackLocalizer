<script setup>
import { computed } from 'vue'
import { ElAlert, ElProgress, ElButton, ElTag } from 'element-plus'
import { useLocalPackStore } from '@/stores/localPack'

const localPackStore = useLocalPackStore()

const stageTextMap = {
  idle: '等待开始',
  discovering: '正在识别目录结构',
  waiting_game_select: '等待选择游戏实例',
  scanning: '正在扫描可翻译内容',
  completed: '扫描完成',
  failed: '扫描失败',
}

const stageText = computed(() => stageTextMap[localPackStore.flowStage] || '处理中')
const result = computed(() => localPackStore.scanResult || {})

function getCandidateModeText(candidate) {
  if (localPackStore.isVersionsCandidatePreferred(candidate)) {
    return '优先使用版本目录'
  }
  if (candidate?.fallback_minecraft_root_usable) {
    return '将回退到 .minecraft 根'
  }
  return '目录不可直接用作工作根'
}
</script>

<template>
  <div class="local-pack-scanner">
    <ElAlert
      v-if="localPackStore.error"
      :title="localPackStore.error"
      type="error"
      closable
      class="scanner-alert"
      @close="localPackStore.error = null"
    />

    <div v-if="localPackStore.scanLoading" class="scanner-loading state-card">
      <div class="state-card__header">
        <div>
          <p class="state-card__eyebrow">扫描中</p>
          <h3 class="state-card__title">正在处理目录结构与可翻译内容</h3>
        </div>
        <ElTag size="small" effect="plain">{{ stageText }}</ElTag>
      </div>
      <ElProgress :percentage="50" :indeterminate="true" :stroke-width="6" />
      <p class="scanner-loading-text">扫描会依次完成结构识别、实例确认与内容统计，请保持当前页面。</p>
    </div>

    <div
      v-else-if="localPackStore.requiresGameSelection"
      class="scanner-selection state-card"
    >
      <div class="state-card__header selection-header">
        <div>
          <p class="state-card__eyebrow">待确认</p>
          <h3 class="state-card__title">选择游戏实例</h3>
        </div>
        <p class="selection-subtitle">检测到多个候选实例，请先明确选择要扫描的实例后再继续。</p>
      </div>

      <div class="candidate-list">
        <button
          v-for="candidate in localPackStore.versionCandidates"
          :key="candidate.game_name"
          type="button"
          class="candidate-card"
          :class="{ 'candidate-card--selected': localPackStore.selectedGameName === candidate.game_name }"
          @click="localPackStore.setSelectedGameName(candidate.game_name)"
        >
          <div class="candidate-card-header">
            <span class="candidate-name">{{ candidate.game_name || '未知实例' }}</span>
            <ElTag size="small" :type="localPackStore.isVersionsCandidatePreferred(candidate) ? 'success' : 'warning'">
              {{ getCandidateModeText(candidate) }}
            </ElTag>
          </div>

          <div class="candidate-meta">
            <div class="candidate-meta-item">
              <span class="candidate-meta-label">MC 版本</span>
              <span class="candidate-meta-value">{{ candidate.mc_version || '未提供版本信息' }}</span>
            </div>
            <div class="candidate-meta-item">
              <span class="candidate-meta-label">来源</span>
              <span class="candidate-meta-value" :class="{ 'candidate-meta-value--empty': !candidate.source_field }">{{ candidate.source_field || '未提供来源字段' }}</span>
            </div>
          </div>

          <div class="candidate-path" :class="{ 'candidate-path--empty': !(candidate.version_work_root || candidate.version_root || localPackStore.minecraftRoot) }">
            {{ candidate.version_work_root || candidate.version_root || localPackStore.minecraftRoot || '未提供候选路径信息' }}
          </div>
        </button>
      </div>

      <div class="selection-actions">
        <ElButton
          type="primary"
          :disabled="!localPackStore.selectedGameName"
          @click="localPackStore.continueScanWithSelectedGame()"
        >
          确认并扫描
        </ElButton>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.local-pack-scanner {
  margin-bottom: var(--notion-spacing-md);
}

.scanner-alert {
  margin-bottom: var(--notion-spacing-md);
}

.state-card,
.result-summary-card,
.result-detail-card {
  background: var(--notion-canvas);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
}

.scanner-loading,
.scanner-selection {
  padding: var(--notion-spacing-xl);
  background: var(--notion-surface-soft);
}

.state-card__header,
.result-summary-card__header,
.result-detail-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--notion-spacing-md);
}

.state-card__eyebrow,
.result-summary-card__eyebrow,
.overview-card__label,
.detail-item__label,
.candidate-meta-label {
  font-size: var(--notion-font-size-micro-uppercase);
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--notion-stone);
}

.state-card__title,
.result-detail-card__title {
  margin: 6px 0 0;
  font-size: var(--notion-font-size-h5);
  font-weight: 600;
  color: var(--notion-ink);
}

.selection-subtitle,
.result-summary-card__desc,
.result-detail-card__desc,
.scanner-loading-text {
  font-size: var(--notion-font-size-body-sm);
  line-height: var(--notion-line-height-body-sm);
  color: var(--notion-steel);
}

.scanner-loading-text {
  margin-top: var(--notion-spacing-sm);
}

.selection-header {
  margin-bottom: var(--notion-spacing-md);
}

.candidate-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: var(--notion-spacing-md);
}

.candidate-card {
  width: 100%;
  text-align: left;
  padding: var(--notion-spacing-md);
  background: var(--notion-canvas);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
  cursor: pointer;
  transition: border-color var(--notion-transition-fast), background var(--notion-transition-fast);

  &:hover {
    border-color: var(--notion-hairline-strong);
    background: var(--notion-surface-soft);
  }
}

.candidate-card--selected {
  border-color: var(--notion-primary);
  background: rgba(86, 69, 212, 0.05);
}

.candidate-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--notion-spacing-sm);
  margin-bottom: var(--notion-spacing-sm);
}

.candidate-name {
  font-size: var(--notion-font-size-body);
  font-weight: 600;
  color: var(--notion-ink);
}

.candidate-meta {
  display: flex;
  gap: var(--notion-spacing-lg);
  margin-bottom: var(--notion-spacing-sm);
}

.candidate-meta-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.candidate-meta-value,
.detail-item__value,
.overview-card__value {
  font-size: var(--notion-font-size-body-sm);
  line-height: var(--notion-line-height-body-sm);
  color: var(--notion-ink);
  font-weight: 600;
}

.candidate-meta-value--empty,
.candidate-path--empty,
.result-name--empty,
.detail-item__value--empty,
.overview-card--empty .overview-card__value {
  color: var(--notion-stone);
  font-weight: 500;
}

.candidate-path,
.detail-item__value--path {
  word-break: break-all;
}

.candidate-path {
  padding-top: var(--notion-spacing-xs);
  border-top: 1px solid var(--notion-hairline);
  font-size: var(--notion-font-size-micro);
  color: var(--notion-steel);
}

.selection-actions {
  margin-top: var(--notion-spacing-md);
  display: flex;
  justify-content: flex-end;
}

.scanner-result {
  display: grid;
  gap: var(--notion-spacing-md);
}

.result-summary-card,
.result-detail-card {
  padding: var(--notion-spacing-lg);
}

.result-name {
  margin: 6px 0 0;
  font-size: var(--notion-font-size-h5);
  font-weight: 600;
  color: var(--notion-ink);
}

.result-overview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--notion-spacing-sm);
  margin-top: var(--notion-spacing-md);
}

.overview-card {
  padding: var(--notion-spacing-md);
  background: var(--notion-surface-soft);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
}

.overview-card--warning {
  background: rgba(221, 91, 0, 0.06);
  border-color: rgba(221, 91, 0, 0.18);
}

.overview-card--success {
  background: rgba(26, 174, 57, 0.05);
  border-color: rgba(26, 174, 57, 0.16);
}

.result-detail-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--notion-spacing-sm);
  margin-top: var(--notion-spacing-md);
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: var(--notion-spacing-md);
  background: var(--notion-surface-soft);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
}

.result-action {
  margin-top: var(--notion-spacing-sm);
}

@media (max-width: 900px) {
  .state-card__header,
  .result-summary-card__header,
  .result-detail-card__header {
    flex-direction: column;
  }

  .result-overview-grid,
  .result-detail-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .scanner-loading,
  .scanner-selection,
  .result-summary-card,
  .result-detail-card {
    padding: var(--notion-spacing-md);
  }

  .candidate-list,
  .result-overview-grid,
  .result-detail-grid {
    grid-template-columns: 1fr;
  }

  .candidate-meta {
    flex-direction: column;
    gap: var(--notion-spacing-sm);
  }
}
</style>
