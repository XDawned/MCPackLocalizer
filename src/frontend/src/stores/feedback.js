import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import {
  confirmTranslation,
  reportIssue,
  getDiagnosis,
  applyFix
} from '@/api/feedback'

export const useFeedbackStore = defineStore('feedback', () => {
  const diagnosis = ref(null)
  const loading = ref(false)
  const error = ref(null)

  const hasDiagnosis = computed(() => diagnosis.value !== null)

  async function confirmTranslation(taskId) {
    loading.value = true
    error.value = null
    try {
      const res = await confirmTranslation(taskId)
      return res.data || res
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '确认翻译失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function reportIssue(taskId, errorLog) {
    loading.value = true
    error.value = null
    try {
      const res = await reportIssue(taskId, { error_log: errorLog })
      return res.data || res
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '报告问题失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function loadDiagnosis(taskId) {
    loading.value = true
    error.value = null
    try {
      const res = await getDiagnosis(taskId)
      diagnosis.value = res.data || res
      return diagnosis.value
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '获取诊断信息失败'
    } finally {
      loading.value = false
    }
  }

  async function applyFix(taskId) {
    loading.value = true
    error.value = null
    try {
      const res = await applyFix(taskId)
      diagnosis.value = res.data || res
      return diagnosis.value
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '应用修复失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  function reset() {
    diagnosis.value = null
    loading.value = false
    error.value = null
  }

  return {
    diagnosis,
    loading,
    error,
    hasDiagnosis,
    confirmTranslation,
    reportIssue,
    loadDiagnosis,
    applyFix,
    reset
  }
})
