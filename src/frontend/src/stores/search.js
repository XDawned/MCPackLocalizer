import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { searchModpacks } from '@/api/search'

/**
 * 搜索状态管理 Store
 * 管理：搜索词、筛选条件、结果列表、分页状态、加载状态
 */
export const useSearchStore = defineStore('search', () => {
  // ========== 搜索参数 ==========
  const query = ref('')
  const sources = ref(['curseforge', 'modrinth'])
  const category = ref(null)
  const modLoader = ref(null)
  const gameVersion = ref(null)
  const sort = ref('relevance')
  const limit = ref(10)

  // ========== 搜索结果 ==========
  const results = ref([])
  const count = ref(0)
  const cursor = ref(null)       // 游标（后端 cursor-based 时使用）
  const offset = ref(0)          // 偏移量（后端 offset-based 时使用）
  const hasMore = ref(false)
  const loading = ref(false)     // 首次搜索加载
  const loadingMore = ref(false) // 加载更多
  const error = ref(null)
  const searched = ref(false)    // 是否已执行过搜索

  // ========== 筛选选项 ==========
  const availableSources = ref([
    { value: 'curseforge', label: 'CurseForge' },
    { value: 'modrinth', label: 'Modrinth' }
  ])

  /**
   * 分类选项 — 双源复合格式: "CurseForgeCategoryID/ModrinthSlug"
   *
   * 三种格式:
   *   "ID/slug"  → 同时筛选 CurseForge (按 ID) 和 Modrinth (按 slug)
   *   "ID/"      → 仅筛选 CurseForge，Modrinth 不限分类
   *   "/slug"    → 仅筛选 Modrinth，CurseForge 不限分类
   *
   * CurseForge categoryId 来自 API 分类枚举，Modrinth slug 来自其 facets 系统。
   */
  const categories = ref([
    { value: '', label: '全部' },
    { value: '4484/multiplayer', label: '多人' },
    { value: '/optimization', label: '性能优化' },
    { value: '4479/challenging', label: '硬核' },
    { value: '4483/combat', label: '战斗' },
    { value: '4478/quests', label: '任务' },
    { value: '4472/technology', label: '科技' },
    { value: '4473/magic', label: '魔法' },
    { value: '4475/adventure', label: '冒险' },
    { value: '/kitchen-sink', label: '水槽包' },
    { value: '4476/', label: '探索' },
    { value: '4477/', label: '小游戏' },
    { value: '4474/', label: '科幻' },
    { value: '4736/', label: '空岛' },
    { value: '5128/', label: '原版改良' },
    { value: '4487/', label: 'FTB' },
    { value: '4480/', label: '基于地图' },
    { value: '4481/lightweight', label: '轻量整合' },
    { value: '4482/', label: '大型整合' }
  ])

  const loaders = ref([
    { value: '1/forge', label: 'Forge' },
    { value: '4/fabric', label: 'Fabric' },
    { value: '6/neoforge', label: 'NeoForge' },
    { value: '5/quilt', label: 'Quilt' }
  ])

  const gameVersions = ref([
    { value: '1.21', label: '1.21' },
    { value: '1.20.1', label: '1.20.1' },
    { value: '1.19.2', label: '1.19.2' },
    { value: '1.18.2', label: '1.18.2' },
    { value: '1.16.5', label: '1.16.5' },
    { value: '1.12.2', label: '1.12.2' },
    { value: '1.7.10', label: '1.7.10' }
  ])

  // ========== 计算属性 ==========
  const hasResults = computed(() => results.value.length > 0)
  const isEmpty = computed(() => searched.value && results.value.length === 0 && !loading.value)

  // ========== 方法 ==========

  /**
   * 执行搜索
   * @param {boolean} append - 是否追加结果（翻页）
   */
  async function doSearch(append = false) {
    if (!append) {
      // 新搜索：重置状态
      results.value = []
      cursor.value = null
      offset.value = 0
      hasMore.value = false
      loading.value = true
      loadingMore.value = false
      error.value = null
    } else {
      loadingMore.value = true
    }

    searched.value = true

    try {
      const params = {
        query: query.value,
        sources: sources.value,
        limit: limit.value,
        sort: sort.value
      }
      if (category.value) params.category = category.value
      if (modLoader.value) params.mod_loader = modLoader.value
      if (gameVersion.value) params.game_version = gameVersion.value

      // 翻页参数：优先使用游标（cursor-based），否则使用偏移量（offset-based）
      if (append) {
        if (cursor.value) {
          params.cursor = cursor.value
        } else {
          params.offset = offset.value
        }
      }

      const response = await searchModpacks(params)
      const data = response.data || response

      if (append) {
        // 按 platform + id 去重，避免 API 数据变化导致重复项
        const rawItems = data.results || data.items || []
        const existingKeys = new Set(
          results.value.map(r => `${r.platform}:${r.id}`)
        )
        const newItems = rawItems.filter(
          item => !existingKeys.has(`${item.platform}:${item.id}`)
        )
        results.value.push(...newItems)
        offset.value += limit.value
      } else {
        results.value = data.results || data.items || []
        offset.value = limit.value
      }

      count.value = data.count || 0
      cursor.value = data.cursor || null
      // has_more：优先使用后端返回值，否则根据已加载数量本地计算
      hasMore.value = data.has_more ?? (results.value.length > 0)
    } catch (e) {
      error.value = e.message || '搜索失败，请检查网络连接'
      // 追加失败不清空已有结果
      if (!append) results.value = []
    } finally {
      loading.value = false
      loadingMore.value = false
    }
  }

  /** 加载更多（翻页） */
  async function loadMore() {
    if (!hasMore.value || loading.value || loadingMore.value) return
    await doSearch(true)
  }

  /** 重置搜索参数 */
  function resetFilters() {
    query.value = ''
    category.value = null
    modLoader.value = null
    gameVersion.value = null
    sort.value = 'relevance'
    sources.value = ['curseforge', 'modrinth']
    results.value = []
    count.value = 0
    cursor.value = null
    offset.value = 0
    hasMore.value = false
    loading.value = false
    loadingMore.value = false
    error.value = null
    searched.value = false
  }

  return {
    // 搜索参数
    query,
    sources,
    category,
    modLoader,
    gameVersion,
    sort,
    limit,
    // 搜索结果
    results,
    count,
    cursor,
    offset,
    hasMore,
    loading,
    loadingMore,
    error,
    searched,
    // 筛选选项
    availableSources,
    categories,
    loaders,
    gameVersions,
    // 计算属性
    hasResults,
    isEmpty,
    // 方法
    doSearch,
    loadMore,
    resetFilters
  }
})
