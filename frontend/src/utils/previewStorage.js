/**
 * 预览页「已生成邮件内容」按用户隔离存 localStorage，避免多销售共用浏览器时串数据。
 */
export const LEGACY_PREVIEW_STORAGE_KEY = 'preview_generated_content'

export function previewStorageKey(userId) {
  if (userId == null || userId === '') return null
  return `preview_generated_content_${userId}`
}

export function loadPreviewGenerated(userId) {
  const k = previewStorageKey(userId)
  if (!k) return {}
  try {
    const raw = localStorage.getItem(k)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

export function savePreviewGenerated(userId, data) {
  const k = previewStorageKey(userId)
  if (!k) return
  try {
    localStorage.setItem(k, JSON.stringify(data))
  } catch {
    /* ignore quota */
  }
}

/** 登出 / 401 时清除当前用户的预览缓存 */
export function clearPreviewGeneratedForUser(userId) {
  const k = previewStorageKey(userId)
  if (k) {
    try {
      localStorage.removeItem(k)
    } catch {
      /* ignore */
    }
  }
}

/** 旧版全局 key，仅用于一次性清理，避免读到其他销售的缓存 */
export function removeLegacyPreviewStorage() {
  try {
    localStorage.removeItem(LEGACY_PREVIEW_STORAGE_KEY)
  } catch {
    /* ignore */
  }
}
