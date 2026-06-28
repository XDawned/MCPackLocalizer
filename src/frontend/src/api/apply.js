import apiClient from '@/api'

function normalizePatchConfig(config = {}) {
  return {
    name: config.name ?? null,
    output_dir: config.output_dir ?? null
  }
}

export function applyTranslation(taskId) {
  return apiClient.post(`/apply/${taskId}`)
}

export function restoreBackup(backupId) {
  return apiClient.post(`/apply/backups/${backupId}/restore`)
}

export function getBackups(params = undefined) {
  return apiClient.get('/apply/backups', { params })
}

export function deleteBackup(backupId) {
  return apiClient.delete(`/apply/backups/${backupId}`)
}

export function generatePatchPackage(taskId, config = {}) {
  return apiClient.post(`/apply/${taskId}/generate-patch`, normalizePatchConfig(config))
}
