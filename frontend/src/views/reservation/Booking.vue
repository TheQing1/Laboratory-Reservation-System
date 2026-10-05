<template>
  <div class="page-container">
    <el-row :gutter="14">
      <el-col :xs="24" :lg="15">
        <el-card shadow="never">
          <div class="card-title">
            提交实验室预约
            <span class="sub">提交后需管理员审核</span>
          </div>

          <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
            <el-form-item label="选择实验室" prop="lab_id">
              <el-select
                v-model="form.lab_id"
                filterable
                placeholder="请选择实验室"
                style="width: 100%"
                @change="onLabChange"
              >
                <el-option
                  v-for="lab in labs"
                  :key="lab.id"
                  :label="`${lab.name}（${lab.location || '位置待补充'} · ${lab.capacity}人）`"
                  :value="lab.id"
                  :disabled="lab.status !== 'available'"
                >
                  <span>{{ lab.name }}</span>
                  <span class="opt-sub">
                    {{ lab.location }} · {{ lab.capacity }}人 ·
                    <span :class="lab.status === 'available' ? 'ok' : 'warn'">{{ lab.status_text }}</span>
                  </span>
                </el-option>
              </el-select>
            </el-form-item>

            <el-form-item label="预约日期" prop="booking_date">
              <el-date-picker
                v-model="form.booking_date"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="选择日期"
                :disabled-date="disabledDate"
                style="width: 100%"
                @change="loadAvailability"
              />
            </el-form-item>

            <el-form-item label="时间段" prop="start_time">
              <div class="time-row">
                <el-time-select
                  v-model="form.start_time"
                  start="06:00"
                  step="00:30"
                  end="23:30"
                  placeholder="开始时间"
                  style="width: 150px"
                />
                <span class="dash">至</span>
                <el-time-select
                  v-model="form.end_time"
                  start="06:00"
                  step="00:30"
                  end="23:30"
                  placeholder="结束时间"
                  style="width: 150px"
                />
                <el-button
                  size="small"
                  :icon="MagicStick"
                  @click="askAi"
                >
                  让 AI 帮我选
                </el-button>
              </div>
            </el-form-item>

            <el-form-item label="使用人数" prop="people_count">
              <el-input-number v-model="form.people_count" :min="1" :max="selectedLab?.capacity || 1000" />
              <span v-if="selectedLab" class="hint">该实验室容量 {{ selectedLab.capacity }} 人</span>
            </el-form-item>

            <el-form-item label="用途说明" prop="purpose">
              <el-input
                v-model="form.purpose"
                type="textarea"
                :rows="3"
                maxlength="255"
                show-word-limit
                placeholder="如：深度学习课程实验 / 毕业设计模型训练"
              />
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="submitting" :icon="Check" @click="onSubmit">
                提交预约申请
              </el-button>
              <el-button :icon="Refresh" @click="resetForm">重置</el-button>
            </el-form-item>
          </el-form>

          <el-alert
            v-if="conflictTip"
            type="warning"
            :closable="false"
            show-icon
            :title="conflictTip"
            class="mt10"
          />
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="9">
        <el-card shadow="never" class="mb14">
          <div class="card-title">
            当日空闲时段
            <span class="sub">点击可直接填充</span>
          </div>
          <div v-if="selectedLab" class="lab-brief">
            <div class="brief-name">{{ selectedLab.name }}</div>
            <div class="brief-meta">
              开放 {{ selectedLab.open_time }}-{{ selectedLab.close_time }} · 容量 {{ selectedLab.capacity }} 人
            </div>
          </div>

          <div v-if="freeSlots.length" class="slot-picker">
            <el-tag
              v-for="slot in freeSlots"
              :key="slot.start"
              class="slot-tag"
              :type="form.start_time === slot.start ? 'primary' : 'success'"
              :effect="form.start_time === slot.start ? 'dark' : 'plain'"
              @click="pickSlot(slot)"
            >
              {{ slot.start }}-{{ slot.end }}
            </el-tag>
          </div>
          <el-empty v-else :description="selectedLab ? '当天已无空闲时段' : '请先选择实验室和日期'" :image-size="60" />

          <el-divider v-if="busyList.length" />
          <div v-if="busyList.length" class="busy-block">
            <div class="section-label">已被占用</div>
            <div class="busy-tags">
              <el-tag v-for="(b, i) in busyList" :key="i" size="small" type="danger" effect="plain">
                {{ b.start_time }}-{{ b.end_time }}（{{ b.status }}）
              </el-tag>
            </div>
          </div>
        </el-card>

        <el-card shadow="never">
          <div class="card-title">我的预约概况</div>
          <div class="mini-stats">
            <div class="mini-item">
              <div class="mini-value">{{ myStats.total }}</div>
              <div class="mini-label">全部</div>
            </div>
            <div class="mini-item">
              <div class="mini-value warn">{{ myStats.pending }}</div>
              <div class="mini-label">待审核</div>
            </div>
            <div class="mini-item">
              <div class="mini-value ok">{{ myStats.approved }}</div>
              <div class="mini-label">已通过</div>
            </div>
            <div class="mini-item">
              <div class="mini-value info">{{ myStats.finished }}</div>
              <div class="mini-label">已完成</div>
            </div>
          </div>
          <el-button link type="primary" @click="router.push('/my-reservations')">
            查看全部预约记录 →
          </el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check, MagicStick, Refresh } from '@element-plus/icons-vue'
import { labApi, reservationApi } from '@/api'

const route = useRoute()
const router = useRouter()

const formRef = ref()
const submitting = ref(false)
const labs = ref([])
const selectedLab = ref(null)
const freeSlots = ref([])
const busyList = ref([])
const conflictTip = ref('')
const myStats = reactive({ total: 0, pending: 0, approved: 0, finished: 0 })

const today = () => new Date().toISOString().slice(0, 10)

const form = reactive({
  lab_id: null,
  booking_date: today(),
  start_time: '',
  end_time: '',
  people_count: 1,
  purpose: '',
})

const rules = {
  lab_id: [{ required: true, message: '请选择实验室', trigger: 'change' }],
  booking_date: [{ required: true, message: '请选择预约日期', trigger: 'change' }],
  start_time: [{ required: true, message: '请选择开始时间', trigger: 'change' }],
  end_time: [{ required: true, message: '请选择结束时间', trigger: 'change' }],
  purpose: [{ required: true, message: '请填写用途说明', trigger: 'blur' }],
}

function disabledDate(d) {
  return d.getTime() < Date.now() - 86400000
}

async function loadLabs() {
  const { data } = await labApi.all()
  labs.value = data.list || []
}

async function loadAvailability() {
  conflictTip.value = ''
  if (!form.lab_id || !form.booking_date) {
    freeSlots.value = []
    busyList.value = []
    return
  }
  try {
    const { data } = await labApi.availability(form.lab_id, form.booking_date)
    freeSlots.value = data.free_slots || []
    busyList.value = data.busy || []
  } catch {
    freeSlots.value = []
    busyList.value = []
  }
}

function onLabChange(id) {
  selectedLab.value = labs.value.find((l) => l.id === id) || null
  form.people_count = 1
  form.start_time = ''
  form.end_time = ''
  loadAvailability()
}

function pickSlot(slot) {
  form.start_time = slot.start
  form.end_time = slot.end
  conflictTip.value = ''
}

async function loadMyStats() {
  try {
    const { data } = await reservationApi.stats()
    Object.assign(myStats, data)
  } catch {
    // 忽略
  }
}

/** 把表单交给 AI 助手继续处理 */
function askAi() {
  const labName = selectedLab.value?.name || ''
  const text = `帮我预约${labName ? ' ' + labName : ''} ${form.booking_date}${
    form.start_time ? ' ' + form.start_time + '-' + form.end_time : ''
  }${form.purpose ? ' 用于' + form.purpose : ''}`
  router.push({ path: '/ai-assistant', query: { q: text.trim() } })
}

async function onSubmit() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  if (form.end_time <= form.start_time) {
    ElMessage.warning('结束时间必须晚于开始时间')
    return
  }
  submitting.value = true
  conflictTip.value = ''
  try {
    const { data } = await reservationApi.create({ ...form })
    ElMessageBox.alert(
      `实验室：${data.lab_name}<br/>时间：${data.booking_date} ${data.time_range}<br/>状态：<b>${data.status_text}</b><br/><br/>管理员审核通过后即可使用，可在「我的预约」查看进度。`,
      '预约提交成功',
      { dangerouslyUseHTMLString: true, confirmButtonText: '知道了' }
    )
    resetForm(false)
    loadAvailability()
    loadMyStats()
  } catch (e) {
    conflictTip.value = e?.message || '预约提交失败，请检查时间是否冲突'
  } finally {
    submitting.value = false
  }
}

function resetForm(keepLab = true) {
  form.start_time = ''
  form.end_time = ''
  form.purpose = ''
  form.people_count = 1
  if (!keepLab) {
    form.lab_id = null
    selectedLab.value = null
    freeSlots.value = []
    busyList.value = []
  }
  formRef.value?.clearValidate()
}

onMounted(async () => {
  await loadLabs()
  // 支持从实验室列表带参数跳转
  const presetLab = Number(route.query.lab)
  if (presetLab && labs.value.some((l) => l.id === presetLab)) {
    form.lab_id = presetLab
    onLabChange(presetLab)
  }
  loadMyStats()
})
</script>

<style scoped>
.opt-sub {
  float: right;
  font-size: 12px;
  color: #909399;
  margin-left: 12px;
}

.opt-sub .ok {
  color: #67c23a;
}
.opt-sub .warn {
  color: #e6a23c;
}

.time-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.dash {
  color: #909399;
}

.hint {
  margin-left: 12px;
  font-size: 12px;
  color: #909399;
}

.mb14 {
  margin-bottom: 14px;
}

.lab-brief {
  background: #f7f9fc;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}

.brief-name {
  font-weight: 600;
  color: #1f2d3d;
}

.brief-meta {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.slot-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.slot-tag {
  cursor: pointer;
}

.busy-block .section-label {
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
}

.busy-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.mini-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  text-align: center;
  margin-bottom: 12px;
}

.mini-value {
  font-size: 20px;
  font-weight: 700;
  color: #409eff;
}

.mini-value.warn {
  color: #e6a23c;
}
.mini-value.ok {
  color: #67c23a;
}
.mini-value.info {
  color: #909399;
}

.mini-label {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

.mt10 {
  margin-top: 10px;
}
</style>
