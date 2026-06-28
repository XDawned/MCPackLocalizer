import { ref, onUnmounted } from 'vue'

function resolveTaskId(taskId) {
  if (taskId && typeof taskId === 'object' && 'value' in taskId) {
    return taskId.value
  }
  return taskId
}

function isTerminalStage(stage) {
  return ['done', 'complete', 'cancelled', 'failed'].includes(stage)
}

function normalizeLogEvent(payload) {
  if (!payload || payload.type !== 'log') {
    return payload
  }

  if (typeof payload.data === 'string') {
    return { ...payload, data: payload.data }
  }

  if (payload.data && typeof payload.data === 'object' && !Array.isArray(payload.data)) {
    return { ...payload, data: payload.data }
  }

  if (typeof payload.message === 'string') {
    return { ...payload, data: payload.message }
  }

  return {
    ...payload,
    data: payload.data ?? ''
  }
}

export function useWebSocket(taskId) {
  const connected = ref(false)
  const progress = ref(null)
  const logEvent = ref(null)
  const errorEvent = ref(null)
  const doneEvent = ref(null)
  const error = ref(null)

  let ws = null
  let reconnectTimer = null
  let manuallyClosed = false

  function connect() {
    const resolvedTaskId = resolveTaskId(taskId)
    if (!resolvedTaskId) return

    manuallyClosed = false

    // 开发模式通过 Vite 代理，生产模式通过后端 serve 前端（同源），都使用相对路径
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const url = `${protocol}//${host}/api/v1/ws/translate/${resolvedTaskId}`

    ws = new WebSocket(url)

    ws.onopen = () => {
      connected.value = true
      error.value = null
    }

    ws.onmessage = (event) => {
      if (event.data === 'pong') {
        return
      }

      try {
        const payload = JSON.parse(event.data)

        if (payload.type === 'progress') {
          progress.value = payload
        } else if (payload.type === 'log') {
          logEvent.value = normalizeLogEvent(payload)
        } else if (payload.type === 'error') {
          errorEvent.value = payload
          error.value = payload.data?.message || null
        } else if (payload.type === 'done' || payload.type === 'complete') {
          doneEvent.value = payload
          progress.value = {
            type: 'progress',
            stage: payload.stage === 'cancelled' ? 'cancelled' : 'complete',
            data: payload.data || {}
          }
        }
      } catch (_) {
        // ignore parse errors
      }
    }

    ws.onerror = () => {
      error.value = 'WebSocket 连接异常'
    }

    ws.onclose = () => {
      connected.value = false
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }

      const terminalStage = doneEvent.value?.stage || progress.value?.stage
      if (!manuallyClosed && !isTerminalStage(terminalStage)) {
        reconnectTimer = setTimeout(() => {
          connect()
        }, 3000)
      }
    }
  }

  function disconnect() {
    manuallyClosed = true
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.close()
      ws = null
    }
    connected.value = false
  }

  onUnmounted(() => {
    disconnect()
  })

  return {
    connected,
    progress,
    logEvent,
    errorEvent,
    doneEvent,
    error,
    connect,
    disconnect
  }
}
