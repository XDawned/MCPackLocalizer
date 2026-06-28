import apiClient from '@/api'

// ==================== 通用设置 ====================

export function getSettings() {
  return apiClient.get('/settings')
}

export function updateSettings(data) {
  return apiClient.put('/settings', data)
}

// ==================== 缓存设置 / 统计 ====================

export function getCacheStats() {
  return apiClient.get('/settings/cache/stats')
}

export function clearCache() {
  return apiClient.delete('/settings/cache')
}

// ==================== AI Provider CRUD ====================

export function getAIProviders() {
  return apiClient.get('/settings/ai/providers')
}

export function getAIProvider(providerId) {
  return apiClient.get(`/settings/ai/providers/${providerId}`)
}

export function createAIProvider(data) {
  return apiClient.post('/settings/ai/providers', data)
}

export function updateAIProvider(providerId, data) {
  return apiClient.put(`/settings/ai/providers/${providerId}`, data)
}

export function deleteAIProvider(providerId) {
  return apiClient.delete(`/settings/ai/providers/${providerId}`)
}

// ==================== AI 模型列表 ====================

export function fetchAIModels(data) {
  return apiClient.post('/settings/ai/models', data)
}

// ==================== AI 连接测试 ====================

export function testAIConnection(data) {
  return apiClient.post('/settings/ai/test', data)
}
