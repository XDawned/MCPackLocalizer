/** Translation task status labels */
export const TASK_STATUS_LABELS = {
  pending: '等待中',
  configuring: '配置中',
  extracting: '提取中',
  translating: '翻译中',
  assembling: '组装中',
  ready_to_apply: '就绪',
  applied: '已应用',
  verified: '已验证',
  needs_fix: '需要修复',
  fixing: '修复中',
  failed: '失败',
  cancelled: '已取消',
  paused: '已暂停'
}

/** Translation pipeline stages */
export const PIPELINE_STAGES = ['extracting', 'translating', 'post_processing', 'assembling']

/** AI provider display names */
export const AI_PROVIDER_LABELS = {
  openai: 'OpenAI',
  anthropic: 'Anthropic Claude',
  deepseek: 'DeepSeek',
  qwen: '通义千问',
  zhipu: '智谱 GLM',
  ollama: 'Ollama'
}

/** Platform display names */
export const PLATFORM_LABELS = {
  curseforge: 'CurseForge',
  modrinth: 'Modrinth'
}
