<template>
  <div class="page-container">
    <el-card shadow="never">
      <div class="card-title">
        我的预约
        <span class="sub">共 {{ total }} 条记录</span>
      </div>

      <el-tabs v-model="query.status" @tab-change="reload">
        <el-tab-pane label="全部" name="" />
        <el-tab-pane :label="`待审核 (${counts.pending})`" name="pending" />
        <el-tab-pane :label="`已通过 (${counts.approved})`" name="approved" />
        <el-tab-pane :label="`已驳回 (${counts.rejected})`" name="rejected" />
        <el-tab-pane :label="`已完成 (${counts.finished})`" name="finished" />
        <el-tab-pane :label="`已取消 (${counts.cancelled})`" name="cancelled" />
      </el-tabs>

      <el-table :data="list" v-loading="loading" stripe>
        <el-table-column prop="lab_name" label="实验室" min-width="150" />
        <el-table-column label="使用时间" min-width="200">
          <template #default="{ row }">
            <div>{{ row.booking_date }}</div>
            <div class="time-sub">{{ row.time_range }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="purpose" label="用途" min-width="180" show-overflow-tooltip />
        <el-table-column prop="people_count" label="人数" width="70" align="center" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small" effect="plain">{{ row.status_text }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="review_remark" label="审核意见" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span :class="{ 'text-muted': !row.review_remark }">{{ row.review_remark || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'pending'"
              size="small"
              link
              type="warning"
              @click="onCancel(row)"
            >
              取消预约
            </el-button>
            <el-button
              v-else-if="row.status === 'approved'"
              size="small"
              link
              type="warning"
              @click="onCancel(row)"
            >
              取消预约
            </el-button>
            <span v-else class="text-muted">—</span>
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
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { reservationApi } from '@/api'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const counts = reactive({ pending: 0, approved: 0, rejected: 0, finished: 0, cancelled: 0 })

const query = reactive({ page: 1, page_size: 10, status: '', mine: true })

function statusType(status) {
  return {
    pending: 'warning',
    approved: 'success',
    rejected: 'danger',
    cancelled: 'info',
    finished: '',
  }[status]
}

async function load() {
  loading.value = true
  try {
    const { data } = await reservationApi.list({ ...query })
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

async function loadCounts() {
  try {
    const { data } = await reservationApi.stats()
    Object.assign(counts, data)
  } catch {
    // 忽略
  }
}

async function onCancel(row) {
  try {
    await ElMessageBox.confirm(
      `确定取消「${row.lab_name}」${row.booking_date} ${row.time_range} 的预约吗？`,
      '取消预约',
      { type: 'warning', confirmButtonText: '确定取消', cancelButtonText: '再想想' }
    )
  } catch {
    return
  }
  await reservationApi.cancel(row.id)
  ElMessage.success('已取消预约')
  load()
  loadCounts()
}

onMounted(() => {
  load()
  loadCounts()
})
</script>

<style scoped>
.time-sub {
  font-size: 12px;
  color: #909399;
}
</style>
