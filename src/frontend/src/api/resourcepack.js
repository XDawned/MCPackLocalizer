import apiClient from '@/api'

function normalizeResourcePackConfig(config = {}) {
  return {
    pack_format: config.pack_format ?? null,
    description: config.description ?? 'MCPackLocalizer 汉化资源包',
    name: config.name ?? null
  }
}

function buildResourcePackDownloadUrl(taskId) {
  const baseURL = (apiClient.defaults.baseURL || '/api/v1').replace(/\/$/, '')
  return `${baseURL}/apply/${taskId}/download-resourcepack`
}

function parseFilenameFromDisposition(contentDisposition, fallback) {
  if (!contentDisposition) return fallback

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch {
      return utf8Match[1]
    }
  }

  const plainMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  return plainMatch?.[1] || fallback
}

async function resolveDownloadError(response) {
  const defaultMessage = `下载资源包失败 (${response.status})`
  const contentType = response.headers.get('content-type') || ''

  try {
    if (contentType.includes('application/json')) {
      const payload = await response.json()
      return payload?.detail || payload?.message || defaultMessage
    }

    const text = await response.text()
    return text || defaultMessage
  } catch {
    return defaultMessage
  }
}

export function generateResourcePack(taskId, config = {}) {
  return apiClient.post(`/apply/${taskId}/generate-resourcepack`, normalizeResourcePackConfig(config))
}

export async function downloadResourcePack(taskId) {
  const response = await fetch(buildResourcePackDownloadUrl(taskId))
  if (!response.ok) {
    throw new Error(await resolveDownloadError(response))
  }

  return {
    data: await response.blob(),
    filename: parseFilenameFromDisposition(
      response.headers.get('content-disposition'),
      `MCPackLocalizer_${taskId}.zip`
    )
  }
}
