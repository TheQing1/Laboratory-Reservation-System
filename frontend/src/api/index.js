import request, { getToken } from './request'

/* ------------------------------- 认证 ------------------------------- */
export const authApi = {
  login: (data) => request.post('/auth/login', data),
  register: (data) => request.post('/auth/register', data),
  me: () => request.get('/auth/me'),
  logout: () => request.post('/auth/logout'),
}

/* ------------------------------- 用户 ------------------------------- */
export const userApi = {
  list: (params) => request.get('/users', { params }),
  create: (data) => request.post('/users', data),
  detail: (id) => request.get(`/users/${id}`),
  update: (id, data) => request.put(`/users/${id}`, data),
  remove: (id) => request.delete(`/users/${id}`),
  toggleStatus: (id, isActive) =>
    request.put(`/users/${id}/status`, null, { params: { is_active: isActive } }),
  updateProfile: (data) => request.put('/users/profile/me', data),
  changePassword: (data) => request.put('/users/password/me', data),
}

/* ------------------------------ 实验室 ------------------------------ */
export const labApi = {
  list: (params) => request.get('/labs', { params }),
  all: () => request.get('/labs', { params: { page: 1, page_size: 100 } }),
  buildings: () => request.get('/labs/buildings'),
  detail: (id) => request.get(`/labs/${id}`),
  availability: (id, date) => request.get(`/labs/${id}/availability`, { params: { date } }),
  create: (data) => request.post('/labs', data),
  update: (id, data) => request.put(`/labs/${id}`, data),
  remove: (id) => request.delete(`/labs/${id}`),
}

/* ------------------------------- 设备 ------------------------------- */
export const equipmentApi = {
  list: (params) => request.get('/equipments', { params }),
  detail: (id) => request.get(`/equipments/${id}`),
  create: (data) => request.post('/equipments', data),
  update: (id, data) => request.put(`/equipments/${id}`, data),
  remove: (id) => request.delete(`/equipments/${id}`),
}

/* ------------------------------- 预约 ------------------------------- */
export const reservationApi = {
  list: (params) => request.get('/reservations', { params }),
  stats: () => request.get('/reservations/stats'),
  detail: (id) => request.get(`/reservations/${id}`),
  create: (data) => request.post('/reservations', data),
  update: (id, data) => request.put(`/reservations/${id}`, data),
  cancel: (id) => request.put(`/reservations/${id}/cancel`),
  review: (id, data) => request.put(`/reservations/${id}/review`, data),
  remove: (id) => request.delete(`/reservations/${id}`),
}

/* ------------------------------ 知识库 ------------------------------ */
export const documentApi = {
  list: (params) => request.get('/documents', { params }),
  categories: () => request.get('/documents/categories'),
  stats: () => request.get('/documents/stats'),
  search: (query, topK = 3) =>
    request.post('/documents/search', null, { params: { query, top_k: topK } }),
  detail: (id) => request.get(`/documents/${id}`),
  create: (data) => request.post('/documents', data),
  update: (id, data) => request.put(`/documents/${id}`, data),
  remove: (id) => request.delete(`/documents/${id}`),
  reindex: () => request.post('/documents/reindex'),
}

/* ---------------------------- 仪表盘 / AI ---------------------------- */
export const dashboardApi = {
  stats: () => request.get('/dashboard/stats'),
  aiStatus: () => request.get('/dashboard/ai-status'),
}

export const chatApi = {
  send: (data) => request.post('/chat', data),
  sessions: () => request.get('/chat/sessions'),
  messages: (sessionId) => request.get(`/chat/sessions/${sessionId}`),
  removeSession: (sessionId) => request.delete(`/chat/sessions/${sessionId}`),
}

/* ------------------------------- 上传 ------------------------------- */
export const uploadApi = {
  image: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request.post('/upload/image', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}

/**
 * SSE 流式对话。
 * 用 fetch 读取 text/event-stream，逐条回调事件对象。
 * @returns {Promise<void>} resolve 表示流正常结束
 */
export async function chatStream({ message, sessionId, useRag = true, useTools = true, onEvent, signal }) {
  const token = getToken()
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      message,
      session_id: sessionId || null,
      use_rag: useRag,
      use_tools: useTools,
    }),
    signal,
  })

  if (!response.ok) {
    throw new Error(`对话请求失败（HTTP ${response.status}）`)
  }
  if (!response.body) {
    throw new Error('当前浏览器不支持流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let sep
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const chunk = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const line = chunk.split('\n').find((l) => l.startsWith('data: '))
      if (!line) continue
      const payload = line.slice(6).trim()
      if (payload === '[DONE]') return
      try {
        onEvent?.(JSON.parse(payload))
      } catch {
        // 忽略无法解析的片段
      }
    }
  }
}
