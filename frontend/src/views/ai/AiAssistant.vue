<template>
  <div class="chat-page">
    <!-- 会话侧栏 -->
    <aside class="session-bar" :class="{ collapsed: sidebarCollapsed }">
      <div class="session-head">
        <el-button type="primary" :icon="Plus" class="new-btn" @click="newSession">新建对话</el-button>
      </div>
      <el-scrollbar class="session-scroll">
        <div
          v-for="s in sessions"
          :key="s.id"
          class="session-item"
          :class="{ active: s.id === sessionId }"
          @click="switchSession(s.id)"
        >
          <el-icon><ChatLineSquare /></el-icon>
          <span class="session-title">{{ s.title }}</span>
          <el-icon class="del-icon" @click.stop="removeSession(s.id)"><Delete /></el-icon>
        </div>
        <el-empty v-if="!sessions.length" description="暂无历史对话" :image-size="60" />
      </el-scrollbar>
      <div class="session-foot">
        <div class="mode-box" :class="mode === 'llm' ? 'is-llm' : 'is-local'">
          <el-icon><component :is="mode === 'llm' ? 'Cpu' : 'Monitor'" /></el-icon>
          <div>
            <div class="mode-name">{{ modeText }}</div>
            <div class="mode-desc">
              {{ mode === 'llm' ? `模型：${modelName}` : '内置工具引擎，无需 API Key' }}
            </div>
          </div>
        </div>
        <div class="tool-count">已接入 {{ tools.length }} 个业务工具</div>
      </div>
    </aside>

    <!-- 对话主区 -->
    <section class="chat-main">
      <header class="chat-header">
        <div class="head-left">
          <el-icon class="toggle" @click="sidebarCollapsed = !sidebarCollapsed">
            <component :is="sidebarCollapsed ? 'Expand' : 'Fold'" />
          </el-icon>
          <div>
            <div class="head-title">
              <el-icon><MagicStick /></el-icon> 实验室 AI 智能助手
            </div>
            <div class="head-sub">查实验室 · 查设备 · 查空闲 · 知识库问答 · 对话式预约</div>
          </div>
        </div>
        <div class="head-right">
          <el-switch v-model="useRag" active-text="知识库" size="small" />
          <el-switch v-model="useTools" active-text="工具调用" size="small" />
          <el-button size="small" :icon="RefreshRight" @click="clearMessages">清屏</el-button>
        </div>
      </header>

      <el-scrollbar ref="scrollRef" class="chat-body">
        <div class="msg-list">
          <!-- 欢迎页 -->
          <div v-if="!messages.length" class="welcome">
            <div class="welcome-emoji">🔬</div>
            <h2>你好，我是实验室智能助手</h2>
            <p>我可以直接查询系统里的真实数据，帮你完成预约。</p>
            <div class="quick-grid">
              <div v-for="q in quickQuestions" :key="q.text" class="quick-card" @click="send(q.text)">
                <div class="quick-icon">{{ q.icon }}</div>
                <div class="quick-text">{{ q.text }}</div>
              </div>
            </div>
          </div>

          <!-- 消息 -->
          <div v-for="(msg, idx) in messages" :key="idx" class="msg" :class="msg.role">
            <div class="avatar">
              <el-avatar v-if="msg.role === 'user'" :size="34">
                {{ userStore.displayName.charAt(0) }}
              </el-avatar>
              <div v-else class="ai-avatar">🤖</div>
            </div>
            <div class="bubble-wrap">
              <!-- 工具调用过程 -->
              <div v-if="msg.steps?.length" class="steps">
                <div
                  v-for="(step, si) in msg.steps"
                  :key="si"
                  class="step"
                  :class="step.type"
                >
                  <el-icon v-if="step.type === 'thought'"><Loading v-if="msg.streaming && si === msg.steps.length - 1" class="spin" /><InfoFilled v-else /></el-icon>
                  <el-icon v-else-if="step.type === 'tool_call'"><Tools /></el-icon>
                  <el-icon v-else-if="step.type === 'tool_result'"><Select /></el-icon>
                  <el-icon v-else><WarningFilled /></el-icon>
                  <span class="step-text">{{ stepText(step) }}</span>
                  <el-link
                    v-if="step.type === 'tool_result' && step.result"
                    type="primary"
                    :underline="false"
                    class="step-more"
                    @click="toggleStep(step)"
                  >
                    {{ step._open ? '收起' : '查看结果' }}
                  </el-link>
                </div>
                <pre v-if="hasOpenResult(msg)" class="step-json">{{ openResultText(msg) }}</pre>
              </div>

              <!-- 回答内容 -->
              <div
                v-if="msg.content"
                class="bubble"
                :class="{ 'is-streaming': msg.streaming }"
              >
                <div class="markdown-body" v-html="renderMarkdown(msg.content)" />
                <span v-if="msg.streaming" class="cursor">▋</span>
              </div>
              <div v-else-if="msg.streaming && !msg.steps?.length" class="bubble typing">
                <span class="dot" /><span class="dot" /><span class="dot" />
              </div>

              <div class="msg-actions">
                <el-tooltip content="复制回答" placement="top">
                  <el-icon class="act" @click="copy(msg.content)"><DocumentCopy /></el-icon>
                </el-tooltip>
                <el-tooltip content="重新生成" placement="top">
                  <el-icon
                    v-if="msg.role === 'assistant' && !msg.streaming && idx === messages.length - 1"
                    class="act"
                    @click="regenerate"
                  >
                    <RefreshRight />
                  </el-icon>
                </el-tooltip>
              </div>
            </div>
          </div>
        </div>
      </el-scrollbar>

      <footer class="chat-input">
        <el-input
          v-model="input"
          type="textarea"
          :rows="2"
          resize="none"
          maxlength="2000"
          placeholder="试试问：人工智能实验室明天有空吗？ / 帮我预约电子电工实验室明天 14:00-16:00 / 实验室违规怎么处理？"
          @keydown.enter.exact.prevent="send()"
        />
        <div class="input-actions">
          <span class="tip">Enter 发送 · Shift+Enter 换行</span>
          <el-button
            v-if="streaming"
            type="danger"
            :icon="VideoPause"
            @click="stop"
          >
            停止
          </el-button>
          <el-button v-else type="primary" :icon="Promotion" :disabled="!input.trim()" @click="send()">
            发送
          </el-button>
        </div>
      </footer>
    </section>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ChatLineSquare, Delete, DocumentCopy, InfoFilled, Loading, MagicStick, Plus,
  Promotion, RefreshRight, Select, Tools, VideoPause, WarningFilled,
} from '@element-plus/icons-vue'
import { chatApi, chatStream, dashboardApi } from '@/api'
import { renderMarkdown } from '@/utils/markdown'
import { useUserStore } from '@/store/user'

const route = useRoute()
const userStore = useUserStore()

const messages = ref([])
const sessions = ref([])
const sessionId = ref(null)
const input = ref('')
const streaming = ref(false)
const useRag = ref(true)
const useTools = ref(true)
const sidebarCollapsed = ref(false)
const scrollRef = ref()
const mode = ref('local')
const modeText = ref('本地助手模式')
const modelName = ref('')
const tools = ref([])
let controller = null
let lastUserMessage = ''

const quickQuestions = [
  { icon: '🏫', text: '学校有哪些实验室？分别在哪里？' },
  { icon: '🕐', text: '人工智能实验室明天有空吗？' },
  { icon: '🖥️', text: 'GPU 服务器在哪个实验室？有几台？' },
  { icon: '📋', text: '实验室安全规定有哪些？' },
  { icon: '📝', text: '帮我预约电子电工实验室明天 14:00-16:00 用于电路实验，6个人' },
  { icon: '🎫', text: '我的预约有哪些？审核通过了吗？' },
]

function stepText(step) {
  if (step.type === 'thought') return step.content || '思考中…'
  if (step.type === 'tool_call') return `调用工具 ${step.tool}（${JSON.stringify(step.args || {})}）`
  if (step.type === 'tool_result') return `${step.tool} 返回结果`
  return step.content || ''
}

function hasOpenResult(msg) {
  return (msg.steps || []).some((s) => s.type === 'tool_result' && s._open)
}

function openResultText(msg) {
  const open = (msg.steps || []).filter((s) => s.type === 'tool_result' && s._open)
  return open.map((s) => `【${s.tool}】\n${JSON.stringify(s.result, null, 2)}`).join('\n\n')
}

function toggleStep(step) {
  step._open = !step._open
}

function scrollToBottom() {
  nextTick(() => {
    const wrap = scrollRef.value?.wrapRef
    if (wrap) wrap.scrollTop = wrap.scrollHeight
  })
}

async function loadStatus() {
  try {
    const { data } = await dashboardApi.aiStatus()
    mode.value = data.mode
    modeText.value = data.mode_text
    modelName.value = data.llm?.model || ''
    tools.value = data.tools || []
  } catch {
    // 忽略
  }
}

async function loadSessions() {
  try {
    const { data } = await chatApi.sessions()
    sessions.value = data || []
  } catch {
    sessions.value = []
  }
}

async function newSession() {
  sessionId.value = null
  messages.value = []
}

async function switchSession(id) {
  if (streaming.value) {
    ElMessage.warning('请先等待当前回答结束')
    return
  }
  try {
    const { data } = await chatApi.messages(id)
    sessionId.value = id
    const list = []
    for (const m of data.messages || []) {
      if (m.role === 'user') {
        list.push({ role: 'user', content: m.content })
      } else if (m.role === 'assistant') {
        list.push({ role: 'assistant', content: m.content })
      } else if (m.role === 'tool' && list.length) {
        const last = list[list.length - 1]
        if (last.role === 'assistant') {
          last.steps = last.steps || []
          last.steps.push({ type: 'tool_call', tool: m.tool_name, args: m.tool_args })
          if (m.tool_result) {
            last.steps.push({ type: 'tool_result', tool: m.tool_name, result: m.tool_result })
          }
        }
      }
    }
    messages.value = list
    scrollToBottom()
  } catch {
    // 已提示
  }
}

async function removeSession(id) {
  try {
    await ElMessageBox.confirm('确定删除该对话记录吗？', '提示', { type: 'warning' })
  } catch {
    return
  }
  await chatApi.removeSession(id)
  ElMessage.success('已删除')
  if (sessionId.value === id) newSession()
  loadSessions()
}

function clearMessages() {
  messages.value = []
  sessionId.value = null
}

async function copy(text) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动选择文本')
  }
}

function stop() {
  controller?.abort()
  streaming.value = false
  const last = messages.value[messages.value.length - 1]
  if (last?.streaming) last.streaming = false
  ElMessage.info('已停止生成')
}

async function regenerate() {
  if (!lastUserMessage) return
  messages.value.pop()
  await send(lastUserMessage, true)
}

/**
 * 发送消息并消费 SSE 事件流。
 * 事件类型：start / mode / thought / tool_call / tool_result / delta / done / error
 */
async function send(text, isRegenerate = false) {
  const content = (text ?? input.value).trim()
  if (!content || streaming.value) return

  lastUserMessage = content
  if (!isRegenerate) {
    messages.value.push({ role: 'user', content })
  }
  input.value = ''

  const assistant = { role: 'assistant', content: '', steps: [], streaming: true }
  messages.value.push(assistant)
  streaming.value = true
  scrollToBottom()

  controller = new AbortController()
  try {
    await chatStream({
      message: content,
      sessionId: sessionId.value,
      useRag: useRag.value,
      useTools: useTools.value,
      signal: controller.signal,
      onEvent: (ev) => {
        switch (ev.type) {
          case 'start':
            if (ev.session_id) sessionId.value = ev.session_id
            break
          case 'mode':
            mode.value = ev.mode
            break
          case 'thought':
            assistant.steps.push({ type: 'thought', content: ev.content })
            break
          case 'tool_call':
            assistant.steps.push({ type: 'tool_call', tool: ev.tool, args: ev.args })
            break
          case 'tool_result':
            assistant.steps.push({ type: 'tool_result', tool: ev.tool, result: ev.result })
            break
          case 'delta':
            assistant.content += ev.content || ''
            break
          case 'error':
            assistant.steps.push({ type: 'error', content: ev.content })
            break
          case 'done':
            if (!assistant.content && ev.content) assistant.content = ev.content
            break
          default:
            break
        }
        scrollToBottom()
      },
    })
  } catch (e) {
    if (e?.name !== 'AbortError') {
      assistant.steps.push({ type: 'error', content: e?.message || '请求失败' })
      if (!assistant.content) assistant.content = '抱歉，服务暂时不可用，请稍后重试。'
    }
  } finally {
    assistant.streaming = false
    streaming.value = false
    controller = null
    scrollToBottom()
    loadSessions()
  }
}

onMounted(async () => {
  await loadStatus()
  await loadSessions()
  // 支持从其它页面带着问题跳转过来
  const preset = route.query.q
  if (preset) {
    input.value = String(preset)
    await send(String(preset))
  }
})
</script>

<style scoped>
.chat-page {
  display: flex;
  height: calc(100vh - 58px);
  background: #fff;
}

/* 会话侧栏 */
.session-bar {
  width: 232px;
  border-right: 1px solid #ebeef5;
  display: flex;
  flex-direction: column;
  background: #fafbfc;
  transition: width 0.22s ease;
  overflow: hidden;
}

.session-bar.collapsed {
  width: 0;
  border-right: none;
}

.session-head {
  padding: 12px;
}

.new-btn {
  width: 100%;
}

.session-scroll {
  flex: 1;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  margin: 2px 8px;
  border-radius: 6px;
  font-size: 13px;
  color: #5a5e66;
  cursor: pointer;
}

.session-item:hover {
  background: #ecf5ff;
}

.session-item.active {
  background: #d9ecff;
  color: #409eff;
  font-weight: 500;
}

.session-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.del-icon {
  opacity: 0;
  color: #f56c6c;
}

.session-item:hover .del-icon {
  opacity: 1;
}

.session-foot {
  padding: 10px 12px;
  border-top: 1px solid #ebeef5;
}

.mode-box {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 12px;
}

.mode-box.is-llm {
  background: #f0f9eb;
  color: #529b2e;
}

.mode-box.is-local {
  background: #fdf6ec;
  color: #b88230;
}

.mode-name {
  font-weight: 600;
}

.mode-desc {
  font-size: 11px;
  opacity: 0.85;
  margin-top: 2px;
}

.tool-count {
  font-size: 11px;
  color: #a8abb2;
  margin-top: 8px;
  text-align: center;
}

/* 主区 */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid #ebeef5;
  background: #fff;
  flex-wrap: wrap;
  gap: 10px;
}

.head-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toggle {
  font-size: 18px;
  cursor: pointer;
  color: #5a5e66;
}

.head-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2d3d;
  display: flex;
  align-items: center;
  gap: 6px;
}

.head-sub {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

.head-right {
  display: flex;
  align-items: center;
  gap: 14px;
}

.chat-body {
  flex: 1;
  background: #f7f9fc;
}

.msg-list {
  padding: 18px 20px 8px;
  max-width: 940px;
  margin: 0 auto;
}

/* 欢迎页 */
.welcome {
  text-align: center;
  padding: 32px 10px;
}

.welcome-emoji {
  font-size: 46px;
}

.welcome h2 {
  font-size: 20px;
  color: #1f2d3d;
  margin: 12px 0 6px;
}

.welcome p {
  color: #909399;
  font-size: 13px;
  margin: 0 0 26px;
}

.quick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 10px;
  text-align: left;
}

.quick-card {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 13px 14px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.quick-card:hover {
  border-color: #409eff;
  box-shadow: 0 4px 14px rgba(64, 158, 255, 0.15);
  transform: translateY(-2px);
}

.quick-icon {
  font-size: 20px;
}

.quick-text {
  font-size: 13px;
  color: #303133;
  line-height: 1.5;
}

/* 消息 */
.msg {
  display: flex;
  gap: 12px;
  margin-bottom: 22px;
}

.msg.user {
  flex-direction: row-reverse;
}

.avatar {
  flex-shrink: 0;
}

.ai-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: linear-gradient(135deg, #409eff, #79bbff);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
}

.bubble-wrap {
  max-width: 78%;
  min-width: 0;
}

.msg.user .bubble-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.bubble {
  padding: 11px 15px;
  border-radius: 10px;
  font-size: 14px;
  background: #fff;
  border: 1px solid #ebeef5;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
}

.msg.user .bubble {
  background: #409eff;
  color: #fff;
  border-color: #409eff;
}

.msg.user .bubble :deep(.markdown-body strong) {
  color: #fff;
}

.cursor {
  animation: blink 1s steps(2, start) infinite;
  color: #409eff;
}

@keyframes blink {
  to {
    visibility: hidden;
  }
}

/* 工具过程 */
.steps {
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.step {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: #909399;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 6px 10px;
}

.step.tool_call {
  color: #409eff;
  border-color: #d9ecff;
  background: #f4faff;
}

.step.tool_result {
  color: #529b2e;
  border-color: #e1f3d8;
  background: #f7fcf4;
}

.step.error {
  color: #f56c6c;
  border-color: #fde2e2;
  background: #fef5f5;
}

.step-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-more {
  font-size: 12px;
  flex-shrink: 0;
}

.step-json {
  background: #282c34;
  color: #abb2bf;
  font-size: 12px;
  padding: 10px 12px;
  border-radius: 6px;
  max-height: 240px;
  overflow: auto;
  margin: 4px 0 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.spin {
  animation: rotate 1s linear infinite;
}

@keyframes rotate {
  to {
    transform: rotate(360deg);
  }
}

.msg-actions {
  display: flex;
  gap: 10px;
  margin-top: 5px;
  opacity: 0;
  transition: opacity 0.2s;
}

.msg:hover .msg-actions {
  opacity: 1;
}

.act {
  cursor: pointer;
  color: #a8abb2;
  font-size: 15px;
}

.act:hover {
  color: #409eff;
}

/* 输入区 */
.chat-input {
  border-top: 1px solid #ebeef5;
  padding: 12px 20px 14px;
  background: #fff;
}

.chat-input :deep(.el-textarea__inner) {
  font-size: 14px;
  border-radius: 8px;
}

.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
}

.tip {
  font-size: 12px;
  color: #a8abb2;
}

/* 打字动画 */
.typing {
  display: flex;
  gap: 4px;
  align-items: center;
  padding: 14px 16px;
}

.typing .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #c0c4cc;
  animation: bounce 1.3s infinite ease-in-out;
}

.typing .dot:nth-child(2) {
  animation-delay: 0.18s;
}
.typing .dot:nth-child(3) {
  animation-delay: 0.36s;
}

@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-5px); }
}
</style>
