import apiClient from '@/api'

export function getGlossaryEntries(params) {
  return apiClient.get('/glossary', { params })
}

export function createGlossaryEntry(data) {
  return apiClient.post('/glossary', data)
}

export function updateGlossaryEntry(id, data) {
  return apiClient.put(`/glossary/${id}`, data)
}

export function deleteGlossaryEntry(id) {
  return apiClient.delete(`/glossary/${id}`)
}

export function importGlossary(data) {
  return apiClient.post('/glossary/import', data)
}
