<template>
  <div class="page-container">
    <el-row :gutter="14" class="stat-row">
      <el-col v-for="c in cards" :key="c.label" :xs="12" :sm="6" :md="6" :lg="6">
        <el-card shadow="never" class="mini-card">
          <div class="mini-value" :style="{ color: c.color }">{{ c.value }}</div>
          <div class="mini-label">{{ c.label }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <div class="card-title">
        预约审核
        <span class="sub">审核结果会同步给申请学生</span>
      </div>

      <el-tabs v-model="query.status" @tab-change="reload">
        <el-tab-pane :label="`待审核 (${counts.pending})`" name="pending" />
        <el-tab-pane label="已通过" name="approved" />
        <el-tab-pane label="已驳回" name="rejected" />
        <el-tab-pane label="已完成" name="finished" />
        <el-tab-pane label="已取消" name="cancelled" />
        <el-tab-pane label="全部" name="" />
      </el-tabs>

      <div class="search-bar">
        <el-input
          v-model="query.keyword"
          placeholder="搜索实验室/申请人/用途"
          :prefix-icon="Search"
          clearable
          style="width: 240px"
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-select v-model="query.lab_id" placeholder="全部实验室" clearable filterable style="width: 200px" @change="reload">
          <el-option v-for="lab in labs" :key="lab.id" :label="lab.name" :value="lab.id" />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          style="width: 260px"
          @change="onDateChange"
        />
        <el-button type="primary" :icon="Search" @click="reload">查询</el-button>
        <el-button :icon="Refresh" @click="reset">重置</el-button>
      </div>

      <el-table :data="list" v-loading="loading" stripe>
        <el-table-column label="申请人" min-width="130">
          <template #default="{ row }">
            <div>{{ row.user_name }}</div>
            <div class="sub-text">@{{ row.username }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="lab_name" label="实验室" min-width="150" />
        <el-table-column label="使用时间" min-width="180">
          <template #default="{ row }">
            <div>{{ row.booking_date }}</div>
            <div class="sub-text">{{ row.time_range }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="purpose" label="用途" min-width="190" show-overflow-tooltip />
        <el-table-column prop="people_count" label="人数" width="70" align="center" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small" effect="plain">{{ row.status_text }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="160">
          <template #default="{ row }">
            <span class="sub-text">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <el-button size="small" link type="success" @click="review(row, 'approved')">通过</el-button>
              <el-button size="small" link type="danger" @click="review(row, 'rejected')">驳回</el-button>
            </template>
            <el-button v-else size="small" link type="primary" @click="showDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="load"
          @size-change="reload"
        />
      </div>
    </el-card>

    <!-- 审核对话框 -->
    <el-dialog v-model="reviewVisible" :title="reviewForm.status === 'approved' ? '通过预约申请' : '驳回预约申请'" width="460px">
      <el-descriptions :column="1" border size="small" class="mb12">
        <el-descriptions-item label="申请人">{{ current?.user_name }}（@{{ current?.username }}）</el-descriptions-item>
        <el-descriptions-item label="实验室">{{ current?.lab_name }}</el-descriptions-item>
        <el-descriptions-item label="使用时间">{{ current?.booking_date }} {{ current?.time_range }}</el-descriptions-item>
        <el-descriptions-item label="用途">{{ current?.purpose }}</el-descriptions-item>
        <el-descriptions-item label="人数">{{ current?.people_count }} 人</el-descriptions-item>
      </el-descriptions>
      <el-form label-width="80px">
        <el-form-item label="审核意见">
          <el-input
            v-model="reviewForm.review_remark"
            type="textarea"
            :rows="3"
            :placeholder="reviewForm.status === 'approved' ? '默认：审核通过' : '请填写驳回原因，如：该时段已有教学任务占用'"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewVisible = false">取消</el-button>
        <el-button :type="reviewForm.status === 'approved' ? 'success' : 'danger'" :loading="saving" @click="submitReview">
          确认{{ reviewForm.status === 'approved' ? '通过' : '驳回' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 详情对话框 -->
    <el-dialog v-model="detailVisible" title="预约详情" width="460px">
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="申请人">{{ current?.user_name }}（@{{ current?.username }}）</el-descriptions-item>
        <el-descriptions-item label="实验室">{{ current?.lab_name }}</el-descriptions-item>
        <el-descriptions-item label="使用时间">{{ current?.booking_date }} {{ current?.time_range }}</el-descriptions-item>
        <el-descriptions-item label="用途">{{ current?.purpose }}</el-descriptions-item>
        <el-descriptions-item label="人数">{{ current?.people_count }} 人</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="statusType(current?.status)" size="small" effect="plain">{{ current?.status_text }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="审核意见">{{ current?.review_remark || '—' }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'
import { labApi, reservationApi } from '@/api'

const loading = ref(false)
const saving = ref(false)
const list = ref([])
const total = ref(0)
const labs = ref([])
const counts = reactive({ pending: 0, approved: 0, rejected: 0, finished: 0, cancelled: 0, total: 0 })
const dateRange = ref([])

const query = reactive({ page: 1, page_size: 10, status: 'pending', keyword: '', lab_id: null, date_from: '', date_to: '' })

const reviewVisible = ref(false)
const detailVisible = ref(false)
const current = ref(null)
const reviewForm = reactive({ status: 'approved', review_remark: '' })

const cards = computed(() => [
  { label: '待审核', value: counts.pending, color: '#e6a23c' },
  { label: '已通过', value: counts.approved, color: '#67c23a' },
  { label: '已驳回', value: counts.rejected, color: '#f56c6c' },
  { label: '累计预约', value: counts.total, color: '#409eff' },
])

function statusType(status) {
  return { pending: 'warning', approved: 'success', rejected: 'danger', cancelled: 'info', finished: '' }[status]
}

function formatTime(t) {
  if (!t) return '—'
  return String(t).replace('T', ' ').slice(0, 16)
}

function onDateChange(val) {
  query.date_from = val?.[0] || ''
  query.date_to = val?.[1] || ''
  reload()
}

async function load() {
  loading.value = true
  try {
    const params = { ...query, lab_id: query.lab_id || undefined }
    const { data } = await reservationApi.list(params)
    list.value = data.list || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}
function reload() {
  query.page = 1
  load()
}
function reset() {
  Object.assign(query, { page: 1, status: 'pending', keyword: '', lab_id: null, date_from: '', date_to: '' })
  dateRange.value = []
  load()
}

async function loadCounts() {
  try {
    const { data } = await reservationApi.stats()
    Object.assign(counts, data)
  } catch {
    // 忽略
  }
}

function review(row, status) {
  current.value = row
  reviewForm.status = status
  reviewForm.review_remark = ''
  reviewVisible.value = true
}

async function submitReview() {
  saving.value = true
  try {
    await reservationApi.review(current.value.id, { ...reviewForm })
    ElMessage.success(reviewForm.status === 'approved' ? '已通过该预约' : '已驳回该预约')
    reviewVisible.value = false
    load()
    loadCounts()
  } catch {
    // 已提示
  } finally {
    saving.value = false
  }
}

function showDetail(row) {
  current.value = row
  detailVisible.value = true
}

onMounted(async () => {
  const { data } = await labApi.all()
  labs.value = data.list || []
  load()
  loadCounts()
})
</script>

<style scoped>
.stat-row {
  margin-bottom: 14px;
}

.mini-card {
  border: none;
  text-align: center;
}

.mini-value {
  font-size: 24px;
  font-weight: 700;
}

.mini-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.sub-text {
  font-size: 12px;
  color: #909399;
}

.mb12 {
  margin-bottom: 12px;
}
</style>
