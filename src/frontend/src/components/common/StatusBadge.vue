<script setup>
import { computed } from 'vue'
import { ElTag } from 'element-plus'

const props = defineProps({
  status: { type: String, required: true },
  size: { type: String, default: 'default' }
})

const statusColorMap = {
  pending: '#6a6a80',
  paused: '#6a6a80',
  configuring: '#6C8EBF',
  extracting: '#6C8EBF',
  translating: '#E67E22',
  processing: '#E67E22',
  assembling: '#9B59B6',
  applying: '#9B59B6',
  ready_to_apply: '#47B853',
  complete: '#47B853',
  ready: '#47B853',
  applied: '#47B853',
  verified: '#47B853',
  needs_fix: '#E74C3C',
  error: '#E74C3C',
  failed: '#E74C3C',
  cancelled: '#6a6a80',
  cached: '#00BCD4',
  translated: '#47B853'
}

const statusGlowMap = {
  ready_to_apply: true,
  complete: true,
  ready: true,
  applied: true,
  translated: true
}

const elType = computed(() => {
  const s = props.status
  if (['ready_to_apply', 'complete', 'ready', 'applied', 'verified', 'translated'].includes(s)) return 'success'
  if (['translating', 'processing'].includes(s)) return 'warning'
  if (['configuring', 'extracting'].includes(s)) return 'info'
  if (['assembling', 'applying'].includes(s)) return 'info'
  if (['needs_fix', 'error', 'failed'].includes(s)) return 'danger'
  if (['pending', 'paused', 'cancelled'].includes(s)) return 'info'
  if (s === 'cached') return 'primary'
  return 'info'
})

const color = computed(() => statusColorMap[props.status] || '#6a6a80')

const hasGlow = computed(() => statusGlowMap[props.status] || false)

const tagStyle = computed(() => {
  const base = { background: color.value + '18', borderColor: color.value + '40', color: color.value }
  if (hasGlow.value) {
    base.boxShadow = `0 0 8px ${color.value}4D`
    base.textShadow = `0 0 6px ${color.value}66`
  }
  return base
})
</script>

<template>
  <ElTag
    :type="elType"
    :size="size"
    :style="tagStyle"
    class="status-badge"
  >
    <slot />
  </ElTag>
</template>

<style lang="scss" scoped>
.status-badge {
  --el-tag-font-size: var(--notion-font-size-caption);
  --el-tag-font-weight: var(--notion-font-weight-semibold);
  --el-tag-border-radius: var(--notion-rounded-full);
  font-family: var(--notion-font-sans);
}
</style>
