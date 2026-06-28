import apiClient from '@/api'

export function confirmTranslation(taskId) {
  return apiClient.post(`/feedback/${taskId}/confirm`)
}

export function reportIssue(taskId, data) {
  return apiClient.post(`/feedback/${taskId}/report`, data)
}

export function getDiagnosis(taskId) {
  return apiClient.get(`/feedback/${taskId}/diagnosis`)
}

export function applyFix(taskId) {
  return apiClient.post(`/feedback/${taskId}/apply-fix`)
}
