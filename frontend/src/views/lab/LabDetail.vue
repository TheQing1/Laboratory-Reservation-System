<template>
  <div class="page-container" v-loading="loading">
    <el-page-header @back="router.back()">
      <template #content>
        <span class="page-title">{{ lab.name || '实验室详情' }}</span>
      </template>
      <template #extra>
        <el-button
          v-if="!userStore.isAdmin && lab.status === 'available'"
          type="primary"
          :icon="Calendar"
          @click="router.push({ path: '/booking', query: { lab: lab.id } })"
        >
          预约该实验室
        </el-button>
      </template>
    </el-page-header>

    <el-row :gutter="14" class="detail-row">
      <el-col :xs="24" :lg="16">
        <el-card shadow="never" class="mb14">
          <div class="lab-head">
            <div class="lab-emoji-box">{{ emoji }}</div>
            <div class="lab-head-main">
              <div class="lab-title">
                {{ lab.name }}
                <el-tag :type="statusType(lab.status)" effect="plain" size="small">
                  {{ lab.status_text }}
                </el-tag>
              </div>
              <div class="lab-sub">{{ lab.code || '—' }}</div>
              <div class="lab-meta-grid">
                <div><el-icon><Location /></el-icon> 位置：{{ lab.location || '待补充' }}</div>
                <div><el-icon><User /></el-icon> 容量：{{ lab.capacity }} 人</div>
                <div><el-icon><Clock /></el-icon> 开放：{{ lab.open_time }} - {{ lab.close_time }}</div>
                <div><el-icon><Cpu /></el-icon> 设备：{{ lab.equipments?.length || 0 }} 类</div>
              </div>
              <div v-if="lab.tags" class="lab-tags">
                <el-tag v-for="t in lab.tags.split(',')" :key="t" size="small" effect="plain" type="info">
                  {{ t }}
                </el-tag>
              </div>
            </div>
          </div>
          <el-divider />
          <div class="section-label">实验室简介</div>
          <p class="desc">{{ lab.description || '暂无简介' }}</p>
        </el-card>

        <el-card shadow="never" class="mb14">
          <div class="card-title">
            设备清单
            <span class="sub">共 {{ lab.equipments?.length || 0 }} 类设备</span>
          </div>
          <el-table :data="lab.equipments || []" stripe size="default">
            <el-table-column prop="name" label="设备名称" min-width="150" />
            <el-table-column prop="model" label="型号/规格" min-width="150" />
            <el-table-column prop="quantity" label="数量" width="80" align="center" />
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="eqStatusType(row.status)" size="small" effect="plain">
                  {{ row.status_text }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="mb14">
          <div class="card-title">
            空闲时段查询
            <span class="sub">每格 30 分钟</span>
          </div>
          <el-date-picker
            v-model="date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            :disabled-date="disabledDate"
            style="width: 100%"
            @change="loadAvailability"
          />
          <div class="slot-legend">
            <span><i class="dot free" /> 空闲</span>
            <span><i class="dot busy" /> 已预约</span>
            <span><i class="dot closed" /> 非开放</span>
          </div>
          <div class="slot-list">
            <div
              v-for="slot in allSlots"
              :key="slot.start"
              class="slot-item"
              :class="slot.state"
            >
              <span>{{ slot.start }} - {{ slot.end }}</span>
              <el-tag v-if="slot.state === 'free'" size="small" type="success" effect="plain">可约</el-tag>
              <el-tag v-else-if="slot.state === 'busy'" size="small" type="danger" effect="plain">已占用</el-tag>
              <el-tag v-else size="small" type="info" effect="plain">未开放</el-tag>
            </div>
          </div>
          <el-empty v-if="!allSlots.length" description="暂无时段数据" :image-size="60" />
        </el-card>

        <el-card shadow="never">
          <div class="card-title">预约须知</div>
          <ul class="notice-list">
            <li>需至少提前 2 小时提交预约，管理员审核通过后生效。</li>
            <li>单次预约 30 分钟至 8 小时，且须在开放时间内。</li>
            <li>请按时到场签到，连续违约将暂停预约权限。</li>
            <li>如需取消，请在开始时间前 2 小时操作。</li>
          </ul>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="更多规定可询问 AI 助手或查看知识库"
          />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Calendar, Clock, Cpu, Location, User } from '@element-plus/icons-vue'
import { labApi } from '@/api'
import { useUserStore } from '@/store/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const lab = ref({})
const date = ref(new Date().toISOString().slice(0, 10))
const freeSlots = ref([])
const busySlots = ref([])

const EMOJI_MAP = [
  [/人工智能|AI|深度/, '🤖'],
  [/化学|分析/, '🧪'],
  [/生物|医学/, '🧬'],
  [/网络|计算机/, '📡'],
  [/电子|电工/, '⚡'],
  [/智能制造|机器人|数控/, '⚙️'],
  [/虚拟现实|VR/, '🕶️'],
]
const emoji = computed(() => {
  const text = `${lab.value.name || ''}${lab.value.tags || ''}`
  for (const [re, e] of EMOJI_MAP) if (re.test(text)) return e
  return '🔬'
})

function statusType(status) {
  return { available: 'success', maintenance: 'warning', disabled: 'info' }[status] || 'info'
}
function eqStatusType(status) {
  return { normal: 'success', repair: 'warning', scrapped: 'info' }[status] || 'info'
}
function disabledDate(d) {
  return d.getTime() < Date.now() - 86400000
}

/** 把开放时间切成 30 分钟格子，标注空闲/占用/未开放 */
const allSlots = computed(() => {
  const open = lab.value.open_time
  const close = lab.value.close_time
  if (!open || !close) return []
  const toMin = (t) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5))
  const toStr = (m) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
  const freeSet = new Set(freeSlots.value.map((s) => s.start))
  const busySet = new Set()
  for (const b of busySlots.value) {
    for (let m = toMin(b.start_time); m < toMin(b.end_time); m += 30) busySet.add(toStr(m))
  }
  const out = []
  for (let m = 0; m < 24 * 60; m += 30) {
    const start = toStr(m)
    const end = toStr(m + 30)
    let state = 'closed'
    if (m >= toMin(open) && m + 30 <= toMin(close)) {
      if (busySet.has(start)) state = 'busy'
      else if (freeSet.has(start)) state = 'free'
      else state = 'busy'
    }
    out.push({ start, end, state })
  }
  return out
})

async function loadLab() {
  loading.value = true
  try {
    const { data } = await labApi.detail(route.params.id)
    lab.value = data
  } catch {
    lab.value = {}
  } finally {
    loading.value = false
  }
}

async function loadAvailability() {
  try {
    const { data } = await labApi.availability(route.params.id, date.value)
    freeSlots.value = data.free_slots || []
    busySlots.value = data.busy || []
  } catch {
    freeSlots.value = []
    busySlots.value = []
  }
}

onMounted(async () => {
  await loadLab()
  await loadAvailability()
})
</script>

<style scoped>
.page-title {
  font-size: 17px;
  font-weight: 600;
}

.detail-row {
  margin-top: 14px;
}

.mb14 {
  margin-bottom: 14px;
  border: none;
}

.lab-head {
  display: flex;
  gap: 16px;
}

.lab-emoji-box {
  width: 76px;
  height: 76px;
  border-radius: 14px;
  background: linear-gradient(135deg, #ecf5ff, #d9ecff);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 36px;
  flex-shrink: 0;
}

.lab-head-main {
  flex: 1;
}

.lab-title {
  font-size: 20px;
  font-weight: 700;
  color: #1f2d3d;
  display: flex;
  align-items: center;
  gap: 10px;
}

.lab-sub {
  font-size: 12px;
  color: #a8abb2;
  margin: 4px 0 12px;
}

.lab-meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px 16px;
  font-size: 13px;
  color: #606266;
}

.lab-meta-grid div {
  display: flex;
  align-items: center;
  gap: 5px;
}

.lab-tags {
  display: flex;
  gap: 6px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.section-label {
  font-size: 14px;
  font-weight: 600;
  color: #1f2d3d;
  margin-bottom: 8px;
}

.desc {
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
  margin: 0;
}

.slot-legend {
  display: flex;
  gap: 14px;
  font-size: 12px;
  color: #909399;
  margin: 12px 0 8px;
}

.slot-legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  display: inline-block;
}
.dot.free { background: #67c23a; }
.dot.busy { background: #f56c6c; }
.dot.closed { background: #dcdfe6; }

.slot-list {
  max-height: 420px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.slot-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 13px;
  border: 1px solid transparent;
}

.slot-item.free {
  background: #f0f9eb;
  border-color: #e1f3d8;
}
.slot-item.busy {
  background: #fef0f0;
  border-color: #fde2e2;
}
.slot-item.closed {
  background: #fafafa;
  border-color: #f0f0f0;
  color: #c0c4cc;
}

.notice-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: #606266;
  line-height: 1.9;
}
</style>
