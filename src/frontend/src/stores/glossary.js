import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import {
  getGlossaryEntries,
  createGlossaryEntry,
  updateGlossaryEntry,
  deleteGlossaryEntry,
  importGlossary
} from '@/api/glossary'

export const useGlossaryStore = defineStore('glossary', () => {
  const entries = ref([])
  const total = ref(0)
  const search = ref('')
  const loading = ref(false)
  const error = ref(null)

  const filteredEntries = computed(() => {
    if (!search.value) return entries.value
    const q = search.value.toLowerCase()
    return entries.value.filter(
      e => (e.source || '').toLowerCase().includes(q) ||
           (e.target || '').toLowerCase().includes(q)
    )
  })

  async function loadEntries(searchTerm, offset = 0, limit = 50) {
    loading.value = true
    error.value = null
    try {
      const params = { offset, limit }
      if (searchTerm) params.search = searchTerm
      const res = await getGlossaryEntries(params)
      const data = res.data || res
      entries.value = data.entries || data.results || data.items || []
      total.value = data.total || entries.value.length
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '加载术语表失败'
    } finally {
      loading.value = false
    }
  }

  async function createEntry(data) {
    loading.value = true
    error.value = null
    try {
      const res = await createGlossaryEntry(data)
      const entry = res.data || res
      entries.value.unshift(entry)
      total.value += 1
      return entry
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '创建术语失败'
    } finally {
      loading.value = false
    }
  }

  async function updateEntry(id, data) {
    loading.value = true
    error.value = null
    try {
      const res = await updateGlossaryEntry(id, data)
      const updated = res.data || res
      const idx = entries.value.findIndex(e => e.id === id)
      if (idx !== -1) entries.value[idx] = updated
      return updated
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '更新术语失败'
    } finally {
      loading.value = false
    }
  }

  async function deleteEntry(id) {
    loading.value = true
    error.value = null
    try {
      await deleteGlossaryEntry(id)
      entries.value = entries.value.filter(e => e.id !== id)
      total.value = Math.max(0, total.value - 1)
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '删除术语失败'
    } finally {
      loading.value = false
    }
  }

  async function importFromCFPA(data) {
    loading.value = true
    error.value = null
    try {
      const res = await importGlossary(data)
      const result = res.data || res
      return result
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '导入术语失败'
    } finally {
      loading.value = false
    }
  }

  function reset() {
    entries.value = []
    total.value = 0
    search.value = ''
    loading.value = false
    error.value = null
  }

  return {
    entries,
    total,
    search,
    loading,
    error,
    filteredEntries,
    loadEntries,
    createEntry,
    updateEntry,
    deleteEntry,
    importFromCFPA,
    reset
  }
})
