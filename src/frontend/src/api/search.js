import apiClient from './index'

/**
 * 搜索整合包
 * @param {Object} params - 搜索参数 (SearchRequest)
 * @param {string} params.query - 搜索关键词
 * @param {string} [params.type] - 搜索类型
 * @param {string} [params.category] - 分类筛选
 * @param {string} [params.mod_loader] - 模组加载器筛选
 * @param {string} [params.game_version] - 游戏版本筛选
 * @param {number} [params.offset] - 偏移量
 * @param {number} [params.limit] - 每页数量
 * @param {string[]} [params.sources] - 搜索来源
 * @returns {Promise<{total: number, results: Array}>}
 */
export function searchModpacks(params) {
  return apiClient.post('/search', params)
}

/**
 * 获取整合包详情
 * @param {string} platform - 平台 (curseforge / modrinth)
 * @param {string} id - 外部平台 ID
 * @returns {Promise<Object>}
 */
export function getModpackDetail(platform, id) {
  return apiClient.get(`/modpacks/${platform}/${id}`)
}

/**
 * 获取整合包版本列表
 * @param {string} platform - 平台
 * @param {string} id - 外部平台 ID
 * @returns {Promise<Array>}
 */
export function getModpackVersions(platform, id) {
  return apiClient.get(`/modpacks/${platform}/${id}/versions`)
}

/**
 * 获取整合包版本详情（含 Mod 清单）
 * @param {string} platform - 平台
 * @param {string} id - 外部平台 ID
 * @param {string} vid - 版本 ID
 * @returns {Promise<Object>}
 */
export function getModpackVersionDetail(platform, id, vid) {
  return apiClient.get(`/modpacks/${platform}/${id}/versions/${vid}`)
}
