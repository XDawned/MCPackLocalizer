import { ref, computed } from 'vue'

export function usePagination(fetchFn, defaultLimit = 20) {
  const offset = ref(0)
  const limit = ref(defaultLimit)
  const total = ref(0)
  const loading = ref(false)
  const loadingMore = ref(false)
  const items = ref([])
  const error = ref(null)

  const page = computed(() => Math.floor(offset.value / limit.value) + 1)
  const totalPages = computed(() => Math.ceil(total.value / limit.value))
  const hasMore = computed(() => items.value.length < total.value)

  async function loadFirst() {
    offset.value = 0
    items.value = []
    loading.value = true
    error.value = null
    try {
      const result = await fetchFn(0, limit.value)
      items.value = result.items || result.entries || []
      total.value = result.total || 0
    } catch (e) {
      error.value = e.message || 'Load failed'
    } finally {
      loading.value = false
    }
  }

  async function loadMore() {
    if (!hasMore.value || loadingMore.value) return
    loadingMore.value = true
    const nextOffset = offset.value + limit.value
    try {
      const result = await fetchFn(nextOffset, limit.value)
      const newItems = result.items || result.entries || []
      items.value.push(...newItems)
      total.value = result.total || 0
      offset.value = nextOffset
    } catch (e) {
      error.value = e.message || 'Load more failed'
    } finally {
      loadingMore.value = false
    }
  }

  function reset() {
    offset.value = 0
    items.value = []
    total.value = 0
    loading.value = false
    loadingMore.value = false
    error.value = null
  }

  return {
    offset, limit, total, loading, loadingMore, items, error,
    page, totalPages, hasMore,
    loadFirst, loadMore, reset
  }
}
