import axios from 'axios'
import { ElMessage } from 'element-plus'

const TOKEN_KEY = 'lab_booking_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

const request = axios.create({
  baseURL: '/api',
  timeout: 90000, // AI 对话可能耗时较长
})

// 请求拦截：带上 JWT
request.interceptors.request.use(
  (config) => {
    const token = getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截：统一解包 {code, message, data}
request.interceptors.response.use(
  (response) => {
    const body = response.data
    // 非统一格式（如文件流）直接返回
    if (body == null || typeof body !== 'object' || !('code' in body)) {
      return body
    }
    if (body.code === 200) {
      return body
    }
    if (body.code === 401) {
      handleUnauthorized(body.message)
      return Promise.reject(new Error(body.message))
    }
    ElMessage.error(body.message || '请求失败')
    return Promise.reject(new Error(body.message || '请求失败'))
  },
  (error) => {
    const status = error.response?.status
    const body = error.response?.data
    if (status === 401 || status === 403) {
      handleUnauthorized(body?.detail || body?.message)
      return Promise.reject(error)
    }
    const message =
      body?.message || body?.detail || error.message || '网络异常，请稍后重试'
    ElMessage.error(message)
    return Promise.reject(error)
  }
)

let redirecting = false
function handleUnauthorized(message) {
  clearToken()
  if (redirecting) return
  redirecting = true
  ElMessage.error(message || '登录状态已失效，请重新登录')
  const redirect = encodeURIComponent(window.location.hash.replace(/^#/, '') || '/')
  setTimeout(() => {
    window.location.hash = `/login?redirect=${redirect}`
    redirecting = false
  }, 600)
}

export default request
