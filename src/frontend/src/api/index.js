import axios from 'axios'

// 开发模式通过 Vite 代理，生产模式通过后端 serve 前端（同源），都使用相对路径
const API_BASE_URL = '/api/v1'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 720000,
  headers: { 'Content-Type': 'application/json' }
})

// 请求拦截器
apiClient.interceptors.request.use(config => {
  return config
}, error => Promise.reject(error))

// 响应拦截器
apiClient.interceptors.response.use(response => {
  const { code, data, message } = response.data
  if (code === 0) return data
  return Promise.reject(new Error(message || '请求失败'))
}, error => {
  return Promise.reject(error)
})

export default apiClient
