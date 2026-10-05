<template>
  <div class="page-container">
    <el-card shadow="never">
      <div class="card-title">
        实验室管理
        <el-button type="primary" :icon="Plus" @click="openDialog()">新增实验室</el-button>
      </div>

      <div class="search-bar">
        <el-input
          v-model="query.keyword"
          placeholder="搜索名称/编号/楼栋"
          :prefix-icon="Search"
          clearable
          style="width: 240px"
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-select v-model="query.status" placeholder="全部状态" clearable style="width: 140px" @change="reload">
          <el-option label="可预约" value="available" />
          <el-option label="维护中" value="maintenance" />
          <el-option label="已停用" value="disabled" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="reload">查询</el-button>
        <el-button :icon="Refresh" @click="reset">重置</el-button>
      </div>

      <el-table :data="list" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="实验室名称" min-width="170" />
        <el-table-column prop="code" label="编号" width="130" />
        <el-table-column prop="location" label="位置" width="150" />
        <el-table-column prop="capacity" label="容量" width="80" align="center" />
        <el-table-column label="开放时间" width="130">
          <template #default="{ row }">{{ row.open_time }}-{{ row.close_time }}</template>
        </el-table-column>
        <el-table-column label="设备数" width="80" align="center">
          <template #default="{ row }">{{ row.equipment_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small" effect="plain">{{ row.status_text }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openDialog(row)">编辑</el-button>
            <el-button size="small" link type="success" @click="manageEquipments(row)">设备</el-button>
            <el-button size="small" link type="danger" @click="onDelete(row)">删除</el-button>
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

    <!-- 新增/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑实验室' : '新增实验室'" width="620px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="98px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="如：人工智能实验室" />
        </el-form-item>
        <el-form-item label="编号" prop="code">
          <el-input v-model="form.code" placeholder="如：LAB-AI-301" />
        </el-form-item>
        <el-row :gutter="10">
          <el-col :span="12">
            <el-form-item label="楼栋" prop="building">
              <el-input v-model="form.building" placeholder="如：信息楼" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="房间号" prop="room">
              <el-input v-model="form.room" placeholder="如：301" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="10">
          <el-col :span="8">
            <el-form-item label="容量" prop="capacity">
              <el-input-number v-model="form.capacity" :min="0" :max="1000" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="开放时间" prop="open_time">
              <el-time-select v-model="form.open_time" start="06:00" step="00:30" end="23:30" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="关闭时间" prop="close_time">
              <el-time-select v-model="form.close_time" start="06:00" step="00:30" end="23:30" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="状态" prop="status">
          <el-radio-group v-model="form.status">
            <el-radio value="available">可预约</el-radio>
            <el-radio value="maintenance">维护中</el-radio>
            <el-radio value="disabled">已停用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="标签" prop="tags">
          <el-input v-model="form.tags" placeholder="英文逗号分隔，如：AI,深度学习" />
        </el-form-item>
        <el-form-item label="简介" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="实验室用途、面向对象等" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 设备快速跳转 -->
    <el-dialog v-model="eqVisible" title="设备管理" width="720px">
      <div class="eq-head">
        <span class="text-strong">{{ currentLab?.name }}</span>
        <el-button type="primary" size="small" :icon="Plus" @click="addEquipment">新增设备</el-button>
      </div>
      <el-table :data="eqList" v-loading="eqLoading" size="small" stripe>
        <el-table-column prop="name" label="设备名称" min-width="140" />
        <el-table-column prop="model" label="型号" min-width="130" />
        <el-table-column prop="quantity" label="数量" width="70" align="center" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="eqStatusType(row.status)" effect="plain">{{ row.status_text }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="editEquipment(row)">编辑</el-button>
            <el-button size="small" link type="danger" @click="removeEquipment(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!eqLoading && !eqList.length" description="该实验室暂无设备" :image-size="60" />
    </el-dialog>

    <!-- 设备编辑 -->
    <el-dialog v-model="eqFormVisible" :title="eqForm.id ? '编辑设备' : '新增设备'" width="480px" append-to-body>
      <el-form ref="eqFormRef" :model="eqForm" :rules="eqRules" label-width="82px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="eqForm.name" placeholder="如：GPU 计算服务器" />
        </el-form-item>
        <el-form-item label="型号" prop="model">
          <el-input v-model="eqForm.model" placeholder="如：NVIDIA A100" />
        </el-form-item>
        <el-form-item label="数量" prop="quantity">
          <el-input-number v-model="eqForm.quantity" :min="0" :max="10000" />
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-select v-model="eqForm.status" style="width: 100%">
            <el-option label="正常" value="normal" />
            <el-option label="维修中" value="repair" />
            <el-option label="已报废" value="scrapped" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注" prop="description">
          <el-input v-model="eqForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="eqFormVisible = false">取消</el-button>
        <el-button type="primary" :loading="eqSaving" @click="saveEquipment">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { equipmentApi, labApi } from '@/api'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const list = ref([])
const total = ref(0)
const query = reactive({ page: 1, page_size: 10, keyword: '', status: '' })

const dialogVisible = ref(false)
const formRef = ref()
const form = reactive({
  id: null, name: '', code: '', building: '', room: '', capacity: 20,
  open_time: '08:00', close_time: '22:00', status: 'available', tags: '', description: '',
})

const rules = {
  name: [{ required: true, message: '请输入实验室名称', trigger: 'blur' }],
  capacity: [{ required: true, message: '请输入容量', trigger: 'blur' }],
}

// 设备
const eqVisible = ref(false)
const eqLoading = ref(false)
const eqList = ref([])
const currentLab = ref(null)
const eqFormVisible = ref(false)
const eqSaving = ref(false)
const eqFormRef = ref()
const eqForm = reactive({ id: null, lab_id: null, name: '', model: '', quantity: 1, status: 'normal', description: '' })
const eqRules = { name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }] }

function statusType(status) {
  return { available: 'success', maintenance: 'warning', disabled: 'info' }[status] || 'info'
}
function eqStatusType(status) {
  return { normal: 'success', repair: 'warning', scrapped: 'info' }[status] || 'info'
}

async function load() {
  loading.value = true
  try {
    const { data } = await labApi.list({ ...query })
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
  Object.assign(query, { page: 1, keyword: '', status: '' })
  load()
}

function openDialog(row) {
  form.id = row?.id || null
  Object.assign(form, {
    name: row?.name || '', code: row?.code || '', building: row?.building || '', room: row?.room || '',
    capacity: row?.capacity ?? 20, open_time: row?.open_time || '08:00', close_time: row?.close_time || '22:00',
    status: row?.status || 'available', tags: row?.tags || '', description: row?.description || '',
  })
  dialogVisible.value = true
}

async function onSave() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const payload = { ...form }
    delete payload.id
    if (form.id) {
      await labApi.update(form.id, payload)
      ElMessage.success('修改成功')
    } else {
      await labApi.create(payload)
      ElMessage.success('新增成功')
    }
    dialogVisible.value = false
    load()
  } catch {
    // 已提示
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确定要删除实验室「${row.name}」吗？该操作不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await labApi.remove(row.id)
    ElMessage.success('删除成功')
    load()
  } catch {
    // 已提示
  }
}

function manageEquipments(row) {
  currentLab.value = row
  eqVisible.value = true
  loadEquipments()
}

async function loadEquipments() {
  eqLoading.value = true
  try {
    const { data } = await equipmentApi.list({ lab_id: currentLab.value.id, page_size: 100 })
    eqList.value = data.list || []
  } finally {
    eqLoading.value = false
  }
}

function addEquipment() {
  Object.assign(eqForm, { id: null, lab_id: currentLab.value.id, name: '', model: '', quantity: 1, status: 'normal', description: '' })
  eqFormVisible.value = true
}
function editEquipment(row) {
  Object.assign(eqForm, {
    id: row.id, lab_id: row.lab_id, name: row.name, model: row.model,
    quantity: row.quantity, status: row.status, description: row.description,
  })
  eqFormVisible.value = true
}
async function saveEquipment() {
  try {
    await eqFormRef.value.validate()
  } catch {
    return
  }
  eqSaving.value = true
  try {
    const payload = { ...eqForm }
    delete payload.id
    if (eqForm.id) {
      await equipmentApi.update(eqForm.id, payload)
      ElMessage.success('设备已更新')
    } else {
      await equipmentApi.create(payload)
      ElMessage.success('设备已新增')
    }
    eqFormVisible.value = false
    loadEquipments()
    load()
  } catch {
    // 已提示
  } finally {
    eqSaving.value = false
  }
}
async function removeEquipment(row) {
  try {
    await ElMessageBox.confirm(`确定删除设备「${row.name}」吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  await equipmentApi.remove(row.id)
  ElMessage.success('删除成功')
  loadEquipments()
  load()
}

onMounted(load)
</script>

<style scoped>
.card-title {
  border: none;
}

.eq-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
</style>
