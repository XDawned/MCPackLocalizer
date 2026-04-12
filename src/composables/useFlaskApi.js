/**
 * Flask API 调用组合式函数
 */
import { ref } from 'vue'
import apiClient from '../api'

export function useFlaskApi() {
  const loading = ref(false)
  const error = ref(null)

  const request = async (method, url, data = null) => {
    loading.value = true
    error.value = null
    try {
      const response = await apiClient({
        method,
        url,
        data,
      })
      return response
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    request,
  }
}