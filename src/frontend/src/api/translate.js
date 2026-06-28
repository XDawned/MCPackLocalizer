import apiClient from '@/api'

export function saveTranslateConfig(data) {
  return apiClient.post('/translate/config', data)
}

export function startTranslation(data) {
  return apiClient.post('/translate/start', data)
}

function normalizeLogStreamEvent(event) {
  if (!event || typeof event !== 'object' || event.type !== 'log') {
    return event
  }

  if (typeof event.data === 'string') {
    return { ...event, data: event.data }
  }

  if (event.data && typeof event.data === 'object' && !Array.isArray(event.data)) {
    return { ...event, data: event.data }
  }

  if (typeof event.message === 'string') {
    return { ...event, data: event.message }
  }

  return {
    ...event,
    data: event.data ?? ''
  }
}

function dispatchStreamEvent(event, handlers = {}) {
  if (!event || typeof event !== 'object') return

  switch (event.type) {
    case 'progress':
      handlers.onProgress?.(event)
      break
    case 'log':
      handlers.onLog?.(normalizeLogStreamEvent(event))
      break
    case 'error':
      if (handlers.onErrorEvent) {
        handlers.onErrorEvent(event)
      } else if (event.data?.fatal !== false) {
        handlers.onError?.(event.data?.message || '翻译过程中发生错误')
      }
      break
    case 'done':
    case 'complete':
      if (handlers.onDone) {
        handlers.onDone(event)
      } else {
        handlers.onComplete?.(event)
      }
      break
    default:
      handlers.onUnknownEvent?.(event)
      break
  }
}

function parseSseChunk(chunk, handlers) {
  const dataLines = chunk
    .split('\n')
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice(5).trim())
    .filter(Boolean)

  if (dataLines.length === 0) {
    return
  }

  const jsonText = dataLines.join('\n')
  try {
    const event = JSON.parse(jsonText)
    dispatchStreamEvent(event, handlers)
  } catch (_) {
    // 忽略损坏的单条 SSE 数据帧，避免整条流被中断
  }
}

/**
 * 流式启动翻译接口 (POST /translate/start/stream)
 * 返回 text/event-stream，需用 fetch + ReadableStream 消费。
 *
 * 事件类型：
 * - progress: 阶段性进度更新
 * - log:      实时结构化日志
 * - error:    错误事件（支持 fatal / non-fatal）
 * - done:     任务完成或中止
 *
 * 为兼容旧调用方，仍兼容 onComplete / onError 回调。
 */
export async function startTranslationStream(data, handlers = {}, signal) {
  const baseURL = apiClient.defaults.baseURL || '/api/v1'
  const url = `${baseURL}/translate/start/stream`

  const notifyTransportError = (message) => {
    if (handlers.onTransportError) {
      handlers.onTransportError(message)
      return
    }
    handlers.onError?.(message)
  }

  let response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
      signal
    })
  } catch (e) {
    if (e.name === 'AbortError') return
    notifyTransportError(e.message || '流式请求发起失败')
    return
  }

  if (!response.ok) {
    let detail = `请求失败: ${response.status} ${response.statusText}`
    try {
      const errBody = await response.json()
      detail = errBody?.detail || errBody?.message || detail
    } catch (_) {
      // ignore
    }
    notifyTransportError(detail)
    return
  }

  if (!response.body) {
    notifyTransportError('服务端未返回可读取的流式响应')
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''

      for (const part of parts) {
        parseSseChunk(part, handlers)
      }
    }

    if (buffer.trim()) {
      parseSseChunk(buffer, handlers)
    }
  } catch (e) {
    if (e.name === 'AbortError') return
    notifyTransportError(e.message || '流式读取异常')
  }
}

export function getTranslationHistory(offset = 0, limit = 50) {
  return apiClient.get('/translate/history', { params: { offset, limit } })
}

export function getTranslationRestoreContext(taskId) {
  return apiClient.get(`/translate/history/${taskId}/restore-context`)
}

export function getTranslateStatus(taskId) {
  return apiClient.get(`/translate/${taskId}/status`)
}

export function pauseTranslation(taskId) {
  return apiClient.post(`/translate/${taskId}/pause`)
}

export function resumeTranslation(taskId) {
  return apiClient.post(`/translate/${taskId}/resume`)
}

export function cancelTranslation(taskId) {
  return apiClient.post(`/translate/${taskId}/cancel`)
}

export function getTranslateItems(taskId, offset = 0, limit = 50) {
  return apiClient.get(`/translate/${taskId}/items`, { params: { offset, limit } })
}
