<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import {
  ElButton,
  ElCard,
  ElAlert,
  ElEmpty,
  ElTag,
  ElCollapse,
  ElCollapseItem,
  ElInput,
  ElMessage,
  vLoading
} from 'element-plus'
import { useFeedbackStore } from '@/stores/feedback'

const route = useRoute()
const feedbackStore = useFeedbackStore()

const taskId = computed(() => route.query.taskId || null)
const showReportTextarea = ref(false)
const errorLog = ref('')
const confirmed = ref(false)
const reporting = ref(false)
const reportSubmitted = ref(false)

const timeline = ref([
  { status: 'done', text: '翻译完成', time: '2026-05-09 10:30' },
  { status: 'done', text: '汉化已应用', time: '2026-05-09 10:32' },
  { status: 'current', text: '等待验证', time: '当前' }
])

const diagnosisCategoryMap = {
  json_format: { type: 'danger', text: 'JSON格式错误' },
  snbt_syntax: { type: 'warning', text: 'SNBT语法错误' },
  term_error: { type: '', text: '术语错误' },
  other: { type: 'info', text: '其他' }
}

const diagnosisTag = computed(() => {
  if (!feedbackStore.diagnosis) return null
  const cat = feedbackStore.diagnosis.category || 'other'
  return diagnosisCategoryMap[cat] || diagnosisCategoryMap.other
})

const activeDiagnosisNames = ref(['1'])

async function handleConfirm() {
  try {
    await feedbackStore.confirmTranslation(taskId.value)
    confirmed.value = true
    timeline.value[2].status = 'done'
    timeline.value[2].text = '已验证'
    ElMessage.success('翻译已验证并记录到缓存')
  } catch {
    // error handled by store
  }
}

function toggleReportTextarea() {
  showReportTextarea.value = !showReportTextarea.value
  if (!showReportTextarea.value) {
    errorLog.value = ''
  }
}

async function handleReport() {
  if (!errorLog.value.trim()) {
    ElMessage.warning('请输入错误描述或日志')
    return
  }
  reporting.value = true
  try {
    await feedbackStore.reportIssue(taskId.value, errorLog.value)
    showReportTextarea.value = false
    reportSubmitted.value = true
    errorLog.value = ''
    await feedbackStore.loadDiagnosis(taskId.value)
    ElMessage.success('问题已提交，正在分析...')
  } catch {
    // error handled by store
  } finally {
    reporting.value = false
  }
}

async function handleApplyFix() {
  try {
    await feedbackStore.applyFix(taskId.value)
    ElMessage.success('修复已应用')
  } catch {
    // error handled by store
  }
}

onMounted(() => {
  if (taskId.value) {
    feedbackStore.loadDiagnosis(taskId.value)
  }
})
</script>

<template>
  <div class="feedback-view" v-loading="feedbackStore.loading">
    <!-- ═══════ Page Header ═══════ -->
      <div class="page-header">
        <h1 class="page-title">翻译效果确认</h1>
      <p class="page-subtitle">启动游戏验证翻译效果，反馈问题或确认质量</p>
    </div>

    <!-- ═══════ No Task ID ═══════ -->
    <ElEmpty v-if="!taskId" description="未指定翻译任务，请从汉化应用页面进入此功能" />

    <!-- ═══════ Content ═══════ -->
    <template v-else>
      <!-- Error Alert -->
      <ElAlert
        v-if="feedbackStore.error"
        :title="feedbackStore.error"
        type="error"
        closable
        show-icon
        class="view-alert"
      />

      <!-- Success State -->
      <div v-if="confirmed" class="notion-card success-card">
        <div class="success-content">
          <div class="success-icon-wrap">
            <svg width="56" height="56" viewBox="0 0 56 56" fill="none">
              <circle cx="28" cy="28" r="26" fill="#d9f3e1" />
              <path d="M16 29l7 7 17-17" stroke="#1aae39" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <h3 class="success-title">翻译已验证并记录到缓存</h3>
          <p class="success-desc">翻译质量已确认，结果已保存。后续可直接复用此缓存。</p>
        </div>
      </div>

      <!-- Confirm / Report Section -->
      <ElCard
        v-if="!confirmed"
        class="notion-card actions-card"
        shadow="never"
      >
        <h3 class="card-heading">确认翻译质量</h3>
        <p class="card-desc">启动游戏验证翻译是否完整、无误。确认后翻译结果将缓存以供后续复用。</p>

        <div class="actions-row">
          <ElButton class="notion-btn notion-btn--primary" @click="handleConfirm">
            确认翻译
          </ElButton>

          <ElButton
            class="notion-btn notion-btn--secondary"
            @click="toggleReportTextarea"
          >
            报告问题
          </ElButton>
        </div>

        <div v-if="showReportTextarea" class="report-area">
          <p class="report-desc">请描述遇到的问题，或粘贴 latest.log 中的相关错误信息</p>
          <ElInput
            v-model="errorLog"
            type="textarea"
            :rows="6"
            :maxlength="2000"
            show-word-limit
            placeholder="例如：游戏启动后崩溃，日志中出现 JSON 解析错误..."
            class="report-textarea"
          />
          <div class="report-actions">
            <ElButton class="notion-btn notion-btn--ghost" @click="toggleReportTextarea">
              取消
            </ElButton>
            <ElButton
              class="notion-btn notion-btn--primary"
              :loading="reporting"
              @click="handleReport"
            >
              提交诊断请求
            </ElButton>
          </div>
        </div>
      </ElCard>

      <!-- AI Diagnosis Section -->
      <ElCard
        v-if="feedbackStore.diagnosis || reportSubmitted"
        class="notion-card diagnosis-card"
        shadow="never"
      >
        <h3 class="card-heading">
          AI 诊断结果
        </h3>

        <template v-if="feedbackStore.diagnosis">
          <ElCollapse v-model="activeDiagnosisNames" class="diagnosis-collapse">
            <ElCollapseItem name="1">
              <template #title>
                <span class="collapse-title">
                  诊断详情
                  <ElTag
                    v-if="diagnosisTag"
                    :type="diagnosisTag.type"
                    size="small"
                    class="diagnosis-category-tag"
                  >
                    {{ diagnosisTag.text }}
                  </ElTag>
                </span>
              </template>

              <div class="diagnosis-body">
                <div v-if="feedbackStore.diagnosis.description" class="diagnosis-field">
                  <span class="diagnosis-label">诊断描述</span>
                  <span class="diagnosis-value">{{ feedbackStore.diagnosis.description }}</span>
                </div>

                <div v-if="feedbackStore.diagnosis.suggested_fix" class="diagnosis-field">
                  <span class="diagnosis-label">建议修复</span>
                  <code class="diagnosis-code">{{ feedbackStore.diagnosis.suggested_fix }}</code>
                </div>

                <div v-if="feedbackStore.diagnosis.fix_status" class="diagnosis-field">
                  <span class="diagnosis-label">修复状态</span>
                  <ElTag
                    :type="feedbackStore.diagnosis.fix_status === 'applied' ? 'success' : ''"
                    size="small"
                  >
                    {{ feedbackStore.diagnosis.fix_status === 'applied' ? '已应用修复' : '待修复' }}
                  </ElTag>
                </div>

                <div class="diagnosis-actions">
                  <ElButton
                    class="notion-btn notion-btn--primary"
                    :disabled="feedbackStore.diagnosis.fix_status === 'applied'"
                    :loading="feedbackStore.loading"
                    @click="handleApplyFix"
                  >
                    应用修复
                  </ElButton>
                </div>
              </div>
            </ElCollapseItem>
          </ElCollapse>
        </template>

        <ElEmpty v-else description="等待诊断结果..." />
      </ElCard>

      <!-- Task Timeline -->
      <ElCard class="notion-card timeline-card" shadow="never">
        <h3 class="card-heading">任务时间线</h3>

        <div class="timeline">
          <div
            v-for="(item, index) in timeline"
            :key="index"
            class="timeline-item"
            :class="{
              'timeline-item--done': item.status === 'done',
              'timeline-item--current': item.status === 'current'
            }"
          >
            <div class="timeline-dot">
              <svg v-if="item.status === 'done'" width="14" height="14" viewBox="0 0 14 14" fill="none" class="timeline-dot-icon">
                <path d="M3 7.5l3 3 5-6" stroke="#1aae39" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <span v-else class="timeline-dot-pulse" />
            </div>
            <div class="timeline-body">
              <span class="timeline-text">{{ item.text }}</span>
              <ElTag
                :type="item.status === 'done' ? 'success' : ''"
                size="small"
                effect="plain"
              >
                {{ item.status === 'done' ? '已完成' : '进行中' }}
              </ElTag>
            </div>
            <div class="timeline-line" v-if="index < timeline.length - 1" />
          </div>
        </div>
      </ElCard>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.feedback-view {
  max-width: 720px;
  margin: 0 auto;
  padding: var(--notion-spacing-xxl) var(--notion-spacing-xl);
  min-height: 100%;
}

/* ── View Alert ────────────────────────────────────── */
.view-alert {
  margin-bottom: var(--notion-spacing-xl);
}

/* ── Page Header ──────────────────────────────────── */
.page-header {
  margin-bottom: var(--notion-spacing-xxl);
}

.page-title {
  font-size: var(--notion-font-size-h3);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0 0 var(--notion-spacing-xxs) 0;
  letter-spacing: var(--notion-ls-h1);
}

.page-subtitle {
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-slate);
  margin: 0;
  line-height: var(--notion-line-height-body-sm);
}

/* ── Notion Card Base ─────────────────────────────── */
.notion-card {
  background: var(--notion-canvas);
  border: 1px solid var(--notion-hairline);
  border-radius: var(--notion-rounded-lg);
  padding: var(--notion-spacing-xl);
  margin-bottom: var(--notion-spacing-md);

  :deep(.el-card__body) {
    padding: 0;
  }
}

.card-heading {
  font-size: var(--notion-font-size-h5);
  font-weight: 600;
  color: var(--notion-ink);
  margin: 0 0 var(--notion-spacing-sm) 0;
}

.card-desc {
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-slate);
  margin: 0 0 var(--notion-spacing-lg) 0;
  line-height: var(--notion-line-height-body);
}

/* ── Success Card ─────────────────────────────────── */
.success-card {
  border-color: rgb(26 174 57 / 0.25);
  text-align: center;
  padding: var(--notion-spacing-xxl);
  animation: fadeInUp 0.5s ease-out;
}

.success-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--notion-spacing-sm);
}

.success-icon-wrap {
  margin-bottom: var(--notion-spacing-xs);
  animation: pulse-glow 2s ease-in-out infinite;
}

@keyframes pulse-glow {
  0%, 100% { filter: drop-shadow(0 0 6px rgba(26, 174, 57, 0.3)); }
  50% { filter: drop-shadow(0 0 18px rgba(26, 174, 57, 0.55)); }
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.success-title {
  font-size: var(--notion-font-size-h4);
  font-weight: 600;
  color: var(--notion-brand-green);
  margin: 0;
}

.success-desc {
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-slate);
  margin: 0;
  line-height: var(--notion-line-height-body);
}

/* ── Confirm / Report Card ────────────────────────── */
.actions-card {
  padding: var(--notion-spacing-xl);
}

.actions-row {
  display: flex;
  gap: var(--notion-spacing-sm);
  flex-wrap: wrap;
}

/* ── Report Textarea ──────────────────────────────── */
.report-area {
  margin-top: var(--notion-spacing-lg);
  padding-top: var(--notion-spacing-lg);
  border-top: 1px solid var(--notion-hairline);
}

.report-desc {
  font-size: var(--notion-font-size-caption);
  color: var(--notion-steel);
  margin: 0 0 var(--notion-spacing-sm) 0;
  line-height: var(--notion-line-height-caption);
}

.report-textarea {
  margin-bottom: var(--notion-spacing-sm);

  :deep(.el-textarea__inner) {
    background: var(--notion-surface);
    border-color: var(--notion-hairline);
    color: var(--notion-ink);
    font-family: var(--notion-font-sans);
    font-size: var(--notion-font-size-caption);
    border-radius: var(--notion-rounded-md);
    resize: vertical;

    &::placeholder {
      color: var(--notion-stone);
    }

    &:focus {
      border-color: var(--notion-primary);
      box-shadow: 0 0 0 2px rgba(86, 69, 212, 0.12);
    }
  }
}

.report-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--notion-spacing-sm);
}

/* ── Diagnosis Card ───────────────────────────────── */
.diagnosis-card {
  padding: var(--notion-spacing-xl);
}

.diagnosis-collapse {
  border: none;

  :deep(.el-collapse-item__header) {
    height: 40px;
    line-height: 40px;
    background: transparent;
    border-bottom: 1px solid var(--notion-hairline-soft);
    font-size: var(--notion-font-size-body-sm);
    font-weight: 500;
    color: var(--notion-ink);
  }

  :deep(.el-collapse-item__wrap) {
    background: transparent;
    border-bottom: 1px solid var(--notion-hairline-soft);
  }

  :deep(.el-collapse-item__content) {
    padding: var(--notion-spacing-md) 0;
    color: var(--notion-ink);
  }
}

.collapse-title {
  display: flex;
  align-items: center;
  gap: var(--notion-spacing-sm);
}

.diagnosis-category-tag {
  font-size: var(--notion-font-size-micro);
}

.diagnosis-body {
  display: flex;
  flex-direction: column;
  gap: var(--notion-spacing-md);
}

.diagnosis-field {
  display: flex;
  flex-direction: column;
  gap: var(--notion-spacing-xxs);
}

.diagnosis-label {
  font-size: var(--notion-font-size-micro);
  font-weight: 500;
  color: var(--notion-stone);
}

.diagnosis-value {
  font-size: var(--notion-font-size-body-sm);
  color: var(--notion-ink);
  line-height: var(--notion-line-height-body);
}

.diagnosis-code {
  background: var(--notion-surface);
  color: var(--notion-primary);
  padding: var(--notion-spacing-sm) var(--notion-spacing-md);
  border-radius: var(--notion-rounded-sm);
  font-family: var(--notion-font-sans);
  font-size: var(--notion-font-size-caption);
  line-height: var(--notion-line-height-body);
  border: 1px solid var(--notion-hairline);
  white-space: pre-wrap;
  word-break: break-word;
}

.diagnosis-actions {
  margin-top: var(--notion-spacing-sm);
}

/* ── Timeline Card ────────────────────────────────── */
.timeline-card {
  padding: var(--notion-spacing-xl);
}

.timeline {
  display: flex;
  flex-direction: column;
}

.timeline-item {
  display: flex;
  align-items: center;
  gap: var(--notion-spacing-sm);
  padding: var(--notion-spacing-sm) 0;
  position: relative;
}

.timeline-dot {
  width: 24px;
  height: 24px;
  border-radius: var(--notion-rounded-full);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--notion-surface);
  border: 1px solid var(--notion-hairline);
}

.timeline-item--done .timeline-dot {
  background: rgba(26, 174, 57, 0.12);
  border-color: rgba(26, 174, 57, 0.25);
}

.timeline-item--current .timeline-dot {
  background: rgba(26, 174, 57, 0.08);
  border-color: rgba(26, 174, 57, 0.35);
}

.timeline-dot-icon {
  display: block;
}

.timeline-dot-pulse {
  width: 8px;
  height: 8px;
  border-radius: var(--notion-rounded-full);
  background: var(--notion-brand-green);
  animation: dot-pulse 1.5s ease-in-out infinite;
}

@keyframes dot-pulse {
  0%, 100% { opacity: 0.4; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}

.timeline-body {
  flex: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.timeline-text {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 500;
  color: var(--notion-ink);
}

.timeline-item--done .timeline-text {
  color: var(--notion-slate);
}

.timeline-item--current .timeline-text {
  color: var(--notion-brand-green);
}

.timeline-line {
  position: absolute;
  left: 12px;
  bottom: -4px;
  width: 1px;
  height: calc(100% - 20px);
  background: var(--notion-hairline);
}

/* ── Notion Button Variants ───────────────────────── */
.notion-btn {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 500;
  border-radius: var(--notion-rounded-md);
  padding: 8px 18px;
  height: auto;
  line-height: var(--notion-line-height-button);
  transition: all var(--notion-transition-normal);
  font-family: var(--notion-font-sans);
}

.notion-btn--primary {
  background: var(--notion-primary);
  border-color: var(--notion-primary);
  color: var(--notion-on-primary);

  &:hover {
    background: var(--notion-primary-pressed);
    border-color: var(--notion-primary-pressed);
    color: var(--notion-on-primary);
  }

  &:active {
    background: var(--notion-primary-deep);
    border-color: var(--notion-primary-deep);
  }
}

.notion-btn--secondary {
  background: transparent;
  border-color: var(--notion-hairline-strong);
  color: var(--notion-ink);

  &:hover {
    background: var(--notion-surface);
    border-color: var(--notion-steel);
    color: var(--notion-ink);
  }
}

.notion-btn--ghost {
  background: transparent;
  border: none;
  color: var(--notion-slate);
  padding: 8px 12px;
  border-radius: var(--notion-rounded-sm);

  &:hover {
    background: var(--notion-surface);
    color: var(--notion-ink);
  }
}

/* ── Responsive ───────────────────────────────────── */
@media (max-width: 640px) {
  .feedback-view {
    padding: var(--notion-spacing-lg) var(--notion-spacing-md);
  }

  .actions-row {
    flex-direction: column;

    .notion-btn {
      width: 100%;
    }
  }

  .report-actions {
    flex-direction: column;

    .notion-btn {
      width: 100%;
    }
  }

  .notion-card {
    padding: var(--notion-spacing-lg);
  }
}
</style>
