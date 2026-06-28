import apiClient from '@/api'

export function discoverPackFolder(localPath) {
  return apiClient.post('/pack-scan/discover', { local_path: localPath })
}

export function scanPackFolder(localPath, gameName = null) {
  const payload = { local_path: localPath }
  if (gameName) {
    payload.game_name = gameName
  }
  return apiClient.post('/pack-scan', payload)
}

export function getScanStatus(scanId) {
  return apiClient.get(`/pack-scan/${scanId}/status`)
}

export function getScanAreas(scanId) {
  return apiClient.get(`/pack-scan/${scanId}/areas`)
}

export function extractContent(scanId, selectedAreas) {
  return apiClient.post(`/pack-scan/${scanId}/extract`, { selected_areas: selectedAreas })
}
