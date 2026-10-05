<template>
  <div class="page-container">
    <el-card shadow="never" class="filter-card">
      <div class="search-bar">
        <el-input
          v-model="query.keyword"
          placeholder="搜索实验室名称、编号、楼栋、标签"
          :prefix-icon="Search"
          clearable
          style="width: 280px"
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-select v-model="query.building" placeholder="全部楼栋" clearable style="width: 150px" @change="reload">
          <el-option v-for="b in buildings" :key="b" :label="b" :value="b" />
        </el-select>
        <el-select v-model="query.status" placeholder="全部状态" clearable style="width: 140px" @change="reload">
          <el-option label="可预约" value="available" />
          <el-option label="维护中" value="maintenance" />
          <el-option label="已停用" value="disabled" />
        </el-select>
        <el-input-number v-model="query.min_capacity" :min="0" :max="500" placeholder="最少人数" style="width: 130px" />
        <el-button type="primary" :icon="Search" @click="reload">查询</el-button>
        <el-button :icon="Refresh" @click="reset">重置</el-button>
        <div class="flex-spacer" />
        <el-radio-group v-model="viewMode" size="default">
          <el-radio-button value="card"><el-icon><Grid /></el-icon></el-radio-button>
          <el-radio-button value="table"><el-icon><List /></el-icon></el-radio-button>
        </el-radio-group>
      </div>
    </el-card>

    <!-- 卡片视图 -->
    <div v-if="viewMode === 'card'" v-loading="loading" class="lab-grid">
      <el-card
        v-for="lab in list"
        :key="lab.id"
        shadow="hover"
        class="lab-card"
        :body-style="{ padding: '0' }"
        @click="router.push(`/labs/${lab.id}`)"
      >
        <div class="lab-cover" :style="coverStyle(lab)">
          <span class="lab-emoji">{{ labEmoji(lab) }}</span>
          <el-tag
            class="lab-status"
            :type="statusType(lab.status)"
            effect="dark"
            size="small"
          >
            {{ lab.status_text }}
          </el-tag>
        </div>
        <div class="lab-body">
          <div class="lab-name">{{ lab.name }}</div>
          <div class="lab-code">{{ lab.code || '—' }}</div>
          <div class="lab-meta">
            <span><el-icon><Location /></el-icon> {{ lab.location || '位置待补充' }}</span>
            <span><el-icon><User /></el-icon> {{ lab.capacity }} 人</span>
          </div>
          <div class="lab-meta">
            <span><el-icon><Clock /></el-icon> {{ lab.open_time }}-{{ lab.close_time }}</span>
            <span><el-icon><Cpu /></el-icon> {{ lab.equipment_count ?? 0 }} 类设备</span>
          </div>
          <div v-if="lab.tags" class="lab-tags">
            <el-tag v-for="t in lab.tags.split(',')" :key="t" size="small" effect="plain" type="info">
              {{ t }}
            </el-tag>
          </div>
          <div class="lab-desc">{{ lab.description || '暂无简介' }}</div>
        </div>
        <div class="lab-actions">
          <el-button type="primary" link @click.stop="router.push(`/labs/${lab.id}`)">查看详情</el-button>
          <el-button
            v-if="!userStore.isAdmin"
            type="success"
            link
            :disabled="lab.status !== 'available'"
            @click.stop="router.push({ path: '/booking', query: { lab: lab.id } })"
          >
            立即预约
          </el-button>
        </div>
      </el-card>
      <el-empty v-if="!loading && !list.length" description="没有找到符合条件的实验室" />
    </div>

    <!-- 表格视图 -->
    <el-card v-else shadow="never">
      <el-table :data="list" v-loading="loading" stripe>
        <el-table-column prop="name" label="实验室名称" min-width="160">
          <template #default="{ row }">
            <el-link type="primary" @click="router.push(`/labs/${row.id}`)">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="编号" width="130" />
        <el-table-column prop="location" label="位置" width="140" />
        <el-table-column prop="capacity" label="容量" width="80" sortable />
        <el-table-column label="开放时间" width="130">
          <template #default="{ row }">{{ row.open_time }}-{{ row.close_time }}</template>
        </el-table-column>
        <el-table-column label="设备" width="80">
          <template #default="{ row }">{{ row.equipment_count ?? 0 }} 类</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small" effect="plain">{{ row.status_text }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="router.push(`/labs/${row.id}`)">详情</el-button>
            <el-button
              v-if="!userStore.isAdmin"
              size="small"
              link
              type="success"
              :disabled="row.status !== 'available'"
              @click="router.push({ path: '/booking', query: { lab: row.id } })"
            >
              预约
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="pagination-bar">
      <el-pagination
        v-model:current-page="query.page"
        v-model:page-size="query.page_size"
        :total="total"
        :page-sizes="[8, 12, 24, 48]"
        layout="total, sizes, prev, pager, next, jumper"
        background
        @current-change="load"
        @size-change="reload"
      />
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Clock, Cpu, Grid, List, Location, Refresh, Search, User } from '@element-plus/icons-vue'
import { labApi } from '@/api'
import { useUserStore } from '@/store/user'

const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const list = ref([])
const total = ref(0)
const buildings = ref([])
const viewMode = ref('card')

const query = reactive({
  page: 1,
  page_size: 12,
  keyword: '',
  building: '',
  status: '',
  min_capacity: 0,
})

const EMOJIS = ['🔬', '🧪', '💻', '🖥️', '⚙️', '🤖', '🧬', '📡']

function labEmoji(lab) {
  const text = `${lab.name}${lab.tags || ''}`
  if (/人工智能|AI|深度/.test(text)) return '🤖'
  if (/化学|分析/.test(text)) return '🧪'
  if (/生物|医学/.test(text)) return '🧬'
  if (/网络|计算机/.test(text)) return '📡'
  if (/电子|电工/.test(text)) return '⚡'
  if (/智能制造|机器人|数控/.test(text)) return '⚙️'
  if (/虚拟现实|VR/.test(text)) return '🕶️'
  return EMOJIS[lab.id % EMOJIS.length]
}

function coverStyle(lab) {
  const palettes = [
    'linear-gradient(135deg,#409eff,#79bbff)',
    'linear-gradient(135deg,#67c23a,#95d475)',
    'linear-gradient(135deg,#e6a23c,#f3d19e)',
    'linear-gradient(135deg,#9c27b0,#ce93d8)',
    'linear-gradient(135deg,#00bcd4,#4dd0e1)',
    'linear-gradient(135deg,#f56c6c,#f89898)',
  ]
  return { background: palettes[(lab.id || 0) % palettes.length] }
}

function statusType(status) {
  return { available: 'success', maintenance: 'warning', disabled: 'info' }[status] || 'info'
}

async function load() {
  loading.value = true
  try {
    const { data } = await labApi.list({ ...query })
    list.value = data.list || []
    total.value = data.total || 0
  } catch {
    list.value = []
  } finally {
    loading.value = false
  }
}

function reload() {
  query.page = 1
  load()
}

function reset() {
  Object.assign(query, { page: 1, keyword: '', building: '', status: '', min_capacity: 0 })
  load()
}

onMounted(async () => {
  load()
  try {
    const { data } = await labApi.buildings()
    buildings.value = data || []
  } catch {
    buildings.value = []
  }
})
</script>

<style scoped>
.filter-card {
  margin-bottom: 14px;
  border: none;
}

.flex-spacer {
  flex: 1;
}

.lab-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(272px, 1fr));
  gap: 14px;
  min-height: 200px;
}

.lab-card {
  border: none;
  cursor: pointer;
  overflow: hidden;
  transition: transform 0.2s, box-shadow 0.2s;
}

.lab-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 20px rgba(31, 45, 61, 0.12) !important;
}

.lab-cover {
  height: 92px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

.lab-emoji {
  font-size: 38px;
  filter: drop-shadow(0 2px 6px rgba(0, 0, 0, 0.15));
}

.lab-status {
  position: absolute;
  top: 10px;
  right: 10px;
}

.lab-body {
  padding: 14px 16px 6px;
}

.lab-name {
  font-size: 16px;
  font-weight: 600;
  color: #1f2d3d;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lab-code {
  font-size: 12px;
  color: #a8abb2;
  margin: 3px 0 10px;
}

.lab-meta {
  display: flex;
  gap: 14px;
  font-size: 12px;
  color: #606266;
  margin-bottom: 7px;
  flex-wrap: wrap;
}

.lab-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.lab-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin: 8px 0;
}

.lab-desc {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
  height: 38px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  margin-top: 4px;
}

.lab-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  border-top: 1px solid #f5f7fa;
}
</style>
