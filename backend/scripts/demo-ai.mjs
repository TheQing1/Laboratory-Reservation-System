// 演示脚本：走前端同样的代理路径，展示 AI 助手的真实回答与「过程可见」
const BASE = 'http://127.0.0.1:5173/api'

async function api(method, path, { token, body } = {}) {
  const res = await fetch(BASE + path, {
    method,
    headers: { 'content-type': 'application/json', ...(token ? { authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  })
  return res.json()
}

const login = await api('POST', '/auth/login', { body: { username: 'student', password: 'student123' } })
const token = login.data.token
console.log(`登录成功：${login.data.user.name}（${login.data.user.role_text}）\n`)

const questions = [
  '进入实验室有什么安全要求？',
  'GPU 服务器在哪个实验室？有几台？',
  '人工智能实验室明天有空吗？',
]

for (const q of questions) {
  const r = await api('POST', '/chat', { token, body: { message: q } })
  console.log('─'.repeat(72))
  console.log(`👤 ${q}`)
  const toolSteps = (r.data.steps || []).filter((s) => s.type === 'tool_call')
  if (toolSteps.length) {
    console.log(`🔧 调用工具：${toolSteps.map((s) => s.tool).join(' → ')}`)
  }
  console.log(`🤖 ${r.data.reply}\n`)
}

// 演示 AI 代提交预约
const d = new Date(Date.now() + 6 * 86400000).toISOString().slice(0, 10)
const avail = await api('GET', `/labs/1/availability?date=${d}`, { token })
const slot = (avail.data.free_slots || []).find((s) => s.start >= '09:00' && s.end <= '17:00')
if (slot) {
  const q = `帮我预约人工智能实验室 ${d} ${slot.start}-${slot.end} 用于模型训练，4个人`
  const r = await api('POST', '/chat', { token, body: { message: q } })
  console.log('─'.repeat(72))
  console.log(`👤 ${q}`)
  console.log(`🔧 调用工具：${(r.data.steps || []).filter((s) => s.type === 'tool_call').map((s) => s.tool).join(' → ')}`)
  console.log(`🤖 ${r.data.reply}\n`)
}

// 验证确实落库
const mine = await api('GET', '/reservations?mine=true&page_size=5', { token })
console.log(`📋 我的预约共 ${mine.data.total} 条，最新一条：`)
const latest = mine.data.list[0]
console.log(`   ${latest.booking_date} ${latest.time_range} · ${latest.lab_name} · ${latest.status_text} · ${latest.purpose}`)
