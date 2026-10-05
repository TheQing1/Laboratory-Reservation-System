<template>
  <div class="page-container" v-loading="loading">
    <!-- 欢迎条 -->
    <el-card shadow="never" class="welcome">
      <div class="welcome-inner">
        <div>
          <div class="hello">
            {{ greeting }}，{{ userStore.displayName }}
            <el-tag size="small" :type="userStore.isAdmin ? 'danger' : 'success'" effect="plain">
              {{ userStore.user?.role_text }}
            </el-tag>
          </div>
          <div class="tip">
            {{ userStore.isAdmin ? '这里是实验室预约全景概览，可前往「预约审核」处理待审申请。' : '选一间实验室，开始你的实验之旅；也可以直接问 AI 助手。' }}
          </div>
        </div>
        <div class="welcome-actions">
          <el-button type="primary" :icon="MagicStick" @click="router.push('/ai-assistant')">
            AI 智能助手
          </el-button>
          <el-button
            :type="userStore.isAdmin ? 'warning' : 'success'"
            :icon="userStore.isAdmin ? Checked : Calendar"
            @click="router.push(userStore.isAdmin ? '/review' : '/booking')"
          >
            {{ userStore.isAdmin ? '去审核' : '去预约' }}
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 指标卡 -->
    <el-row :gutter="14" class="stat-row">
      <el-col v-for="card in statCards" :key="card.label" :xs="12" :sm="8" :md="6" :lg="3">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-inner">
            <div class="stat-icon" :style="{ background: card.bg, color: card.color }">
              <el-icon :size="20"><component :is="card.icon" /></el-icon>
            </div>
            <div>
              <div class="stat-value">{{ card.value }}</div>
              <div class="stat-label">{{ card.label }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="14">
      <el-col :xs="24" :lg="16">
        <el-card shadow="never" class="chart-card">
          <div class="card-title">
            近 7 天预约趋势
            <span class="sub">按预约使用日期统计</span>
          </div>
          <div ref="trendRef" class="chart" />
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="chart-card">
          <div class="card-title">预约状态分布</div>
          <div ref="pieRef" class="chart" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="14">
      <el-col :xs="24" :lg="12">
        <el-card shadow="never" class="chart-card">
          <div class="card-title">
            今日推荐实验室
            <span class="sub">按空闲程度排序</span>
          </div>
          <div v-if="stats.recommended?.length" class="recommend-list">
            <div
              v-for="lab in stats.recommended"
              :key="lab.id"
              class="recommend-item"
              @click="router.push(`/labs/${lab.id}`)"
            >
              <div class="rec-main">
                <div class="rec-name">
                  {{ lab.name }}
                  <el-tag v-if="lab.busy_today" size="small" type="warning" effect="plain">今日有预约</el-tag>
                  <el-tag v-else size="small" type="success" effect="plain">今日空闲</el-tag>
                </div>
                <div class="rec-meta">
                  <el-icon><Location /></el-icon> {{ lab.location || '位置待补充' }}
                  <el-divider direction="vertical" />
                  <el-icon><User /></el-icon> {{ lab.capacity }} 人
                  <el-divider direction="vertical" />
                  <el-icon><Clock /></el-icon> {{ lab.open_time }}-{{ lab.close_time }}
                </div>
              </div>
              <div class="rec-right">
                <div class="rec-count">{{ lab.free_slot_count }}</div>
                <div class="rec-count-label">个空闲时段</div>
              </div>
            </div>
          </div>
          <el-empty v-else description="暂无可用实验室" :image-size="70" />
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="12">
        <el-card shadow="never" class="chart-card">
          <div class="card-title">
            实验室热度 Top5
            <span class="sub">按累计预约次数</span>
          </div>
          <div ref="barRef" class="chart" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import {
  Calendar, Checked, Clock, Cpu, Location, MagicStick, OfficeBuilding,
  Tickets, User, UserFilled,
} from '@element-plus/icons-vue'
import { dashboardApi } from '@/api'
import { useUserStore } from '@/store/user'

const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const stats = reactive({
  total_labs: 0,
  available_labs: 0,
  total_users: 0,
  total_reservations: 0,
  pending_reservations: 0,
  today_reservations: 0,
  total_equipments: 0,
  status_distribution: [],
  trend: [],
  hot_labs: [],
  recommended: [],
})

const trendRef = ref()
const pieRef = ref()
const barRef = ref()
let trendChart = null
let pieChart = null
let barChart = null

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const statCards = computed(() => {
  const base = [
    { label: '实验室总数', value: stats.total_labs, icon: 'OfficeBuilding', color: '#409eff', bg: '#ecf5ff' },
    { label: '可预约实验室', value: stats.available_labs, icon: 'Select', color: '#67c23a', bg: '#f0f9eb' },
    { label: '设备总数', value: stats.total_equipments, icon: 'Cpu', color: '#e6a23c', bg: '#fdf6ec' },
    { label: '今日预约', value: stats.today_reservations, icon: 'Calendar', color: '#909399', bg: '#f4f4f5' },
  ]
  if (userStore.isAdmin) {
    return [
      ...base,
      { label: '注册用户', value: stats.total_users, icon: 'UserFilled', color: '#9c27b0', bg: '#f5eefd' },
      { label: '累计预约', value: stats.total_reservations, icon: 'Tickets', color: '#00bcd4', bg: '#e6f9fb' },
      { label: '待审核', value: stats.pending_reservations, icon: 'Checked', color: '#f56c6c', bg: '#fef0f0' },
      { label: '已通过', value: stats.approved_reservations, icon: 'CircleCheck', color: '#67c23a', bg: '#f0f9eb' },
    ]
  }
  return [
    ...base,
    { label: '我的预约', value: stats.my_total ?? 0, icon: 'Tickets', color: '#9c27b0', bg: '#f5eefd' },
    { label: '待审核', value: stats.my_pending ?? 0, icon: 'Clock', color: '#f56c6c', bg: '#fef0f0' },
    { label: '已通过', value: stats.my_approved ?? 0, icon: 'CircleCheck', color: '#67c23a', bg: '#f0f9eb' },
    { label: '已完成', value: stats.my_finished ?? 0, icon: 'Finished', color: '#00bcd4', bg: '#e6f9fb' },
  ]
})

function renderTrend() {
  if (!trendRef.value) return
  trendChart = trendChart || echarts.init(trendRef.value)
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 24, bottom: 30 },
    xAxis: {
      type: 'category',
      data: stats.trend.map((t) => t.label),
      axisLine: { lineStyle: { color: '#dcdfe6' } },
      axisLabel: { color: '#909399' },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: '#f0f2f5' } },
      axisLabel: { color: '#909399' },
    },
    series: [
      {
        name: '预约数',
        type: 'line',
        smooth: true,
        symbolSize: 7,
        data: stats.trend.map((t) => t.count),
        itemStyle: { color: '#409eff' },
        lineStyle: { width: 3 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(64,158,255,0.35)' },
            { offset: 1, color: 'rgba(64,158,255,0.02)' },
          ]),
        },
      },
    ],
  })
}

function renderPie() {
  if (!pieRef.value) return
  pieChart = pieChart || echarts.init(pieRef.value)
  const data = (stats.status_distribution || []).map((s) => ({
    name: s.status_text,
    value: s.count,
  }))
  pieChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, icon: 'circle', textStyle: { color: '#606266' } },
    color: ['#e6a23c', '#67c23a', '#f56c6c', '#909399', '#409eff'],
    series: [
      {
        type: 'pie',
        radius: ['42%', '66%'],
        center: ['50%', '44%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
        label: { formatter: '{b}\n{c}' },
        data: data.length ? data : [{ name: '暂无数据', value: 1 }],
      },
    ],
  })
}

function renderBar() {
  if (!barRef.value) return
  barChart = barChart || echarts.init(barRef.value)
  const labs = stats.hot_labs || []
  barChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 8, right: 30, top: 16, bottom: 10, containLabel: true },
    xAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#f0f2f5' } } },
    yAxis: {
      type: 'category',
      data: labs.map((l) => l.name).reverse(),
      axisLine: { lineStyle: { color: '#dcdfe6' } },
      axisLabel: { color: '#606266' },
    },
    series: [
      {
        type: 'bar',
        data: labs.map((l) => l.count).reverse(),
        barWidth: 14,
        itemStyle: {
          borderRadius: [0, 7, 7, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: '#79bbff' },
            { offset: 1, color: '#409eff' },
          ]),
        },
        label: { show: true, position: 'right', color: '#909399' },
      },
    ],
  })
}

function resizeAll() {
  trendChart?.resize()
  pieChart?.resize()
  barChart?.resize()
}

async function load() {
  loading.value = true
  try {
    const { data } = await dashboardApi.stats()
    Object.assign(stats, data)
    await nextTick()
    renderTrend()
    renderPie()
    renderBar()
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  window.addEventListener('resize', resizeAll)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeAll)
  trendChart?.dispose()
  pieChart?.dispose()
  barChart?.dispose()
})
</script>

<style scoped>
.welcome {
  margin-bottom: 14px;
  border: none;
  background: linear-gradient(120deg, #eaf4ff 0%, #f7fbff 100%);
}

.welcome-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.hello {
  font-size: 19px;
  font-weight: 600;
  color: #1f2d3d;
  display: flex;
  align-items: center;
  gap: 8px;
}

.tip {
  font-size: 13px;
  color: #7b8794;
  margin-top: 6px;
}

.welcome-actions {
  display: flex;
  gap: 10px;
}

.stat-row {
  margin-bottom: 4px;
}

.stat-card {
  margin-bottom: 14px;
  border: none;
}

.stat-inner {
  display: flex;
  align-items: center;
  gap: 12px;
}

.stat-icon {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: #1f2d3d;
  line-height: 1.15;
}

.stat-label {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

.chart-card {
  margin-bottom: 14px;
  border: none;
}

.chart {
  width: 100%;
  height: 268px;
}

.recommend-list {
  display: flex;
  flex-direction: column;
}

.recommend-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
  border-bottom: 1px solid #f5f7fa;
}

.recommend-item:last-child {
  border-bottom: none;
}

.recommend-item:hover {
  background: #f5f9ff;
}

.rec-name {
  font-size: 15px;
  font-weight: 600;
  color: #1f2d3d;
  display: flex;
  align-items: center;
  gap: 8px;
}

.rec-meta {
  font-size: 12px;
  color: #909399;
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.rec-right {
  text-align: right;
  flex-shrink: 0;
}

.rec-count {
  font-size: 20px;
  font-weight: 700;
  color: #409eff;
  line-height: 1.1;
}

.rec-count-label {
  font-size: 11px;
  color: #909399;
}
</style>
