/**
 * API 客户端
 */
import axios from 'axios'

const API_BASE_URL = window.flaskAPI?.baseUrl || 'http://127.0.0.1:5000/api'

/**
 * 创建 Axios 实例
 */
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/**
 * 请求拦截器
 */
apiClient.interceptors.request.use(
  (config) => {
    // 可在请求前添加 token 等
    return config
  },
  (error) => {
    console.error('Request error:', error)
    return Promise.reject(error)
  }
)

/**
 * 响应拦截器
 */
apiClient.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    if (error.response) {
      console.error('API Error:', error.response.status, error.response.data)
    } else if (error.request) {
      console.error('No response received:', error.request)
    } else {
      console.error('Request error:', error.message)
    }
    return Promise.reject(error)
  }
)

/**
 * API 方法封装
 */
export const api = {
  // 健康检查
  health: () => apiClient.get('/health'),
  
  // 整合包相关
  modpack: {
    scan: (folder) => apiClient.post('/modpack/scan', { folder }),
    extract: (data) => apiClient.post('/modpack/extract', data),
    check: () => apiClient.get('/modpack/check'),
  },
  
  // 翻译相关
  translation: {
    translate: (texts, options = {}) => apiClient.post('/translation/translate', {
      texts,
      from_lang: options.fromLang || 'en',
      to_lang: options.toLang || 'zh',
      api_type: options.apiType || 'baidu',
      api_key: options.apiKey,
      api_secret: options.apiSecret,
    }),
    parse: (filePath) => apiClient.post('/translation/parse', { file_path: filePath }),
    save: (filePath, content, fileType = 'json') => apiClient.post('/translation/save', {
      file_path: filePath,
      content,
      file_type: fileType,
    }),
    saveCache: (filePath, data) => apiClient.post('/translation/cache/save', {
      file_path: filePath,
      data,
    }),
    loadCache: (filePath) => apiClient.post('/translation/cache/load', { file_path: filePath }),
  },
  
  // 资源包相关
  resourcepack: {
    generate: (data) => apiClient.post('/resourcepack/generate', data),
    download: (filename) => `${API_BASE_URL}/resourcepack/download/${filename}`,
  },
  
  // 设置相关
  settings: {
    get: () => apiClient.get('/settings/get'),
    save: (config) => apiClient.post('/settings/save', config),
    reset: () => apiClient.post('/settings/reset'),
  },
}

export default apiClient