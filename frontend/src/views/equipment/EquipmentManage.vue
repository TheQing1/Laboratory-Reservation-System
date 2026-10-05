<template>
  <div class="page-container">
    <el-card shadow="never">
      <div class="card-title">
        设备管理
        <span class="sub">维护各实验室的设备清单</span>
      </div>

      <div class="search-bar">
        <el-input
          v-model="query.keyword"
          placeholder="搜索设备名称/型号"
          :prefix-icon="Search"
          clearable
          style="width: 240px"
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-select v-model="query.lab_id" placeholder="全部实验室" clearable filterable style="width: 210px" @change="reload">
          <el-option v-for="lab in labs" :key="lab.id" :label="lab.name" :value="lab.id" />
        </el-select>
        <el-select v-model="query.status" placeholder="全部状态" clearable style="width: 140px" @change="reload">
          <el-option label="正常" value="normal" />
          <el-option label="维修中" value="repair" />
          <el-option label="已报废" value="scrapped" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="reload">查询</el-button>
        <el-button :icon="Refresh" @click="reset">重置</el-button>
        <div class="flex-spacer" />
        <el-button type="primary" :icon="Plus" @click="openDialog()">新增设备</el-button>
      </div>

      <el-table :data="list" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="设备名称" min-width="160" />
        <el-table-column prop="model" label="型号/规格" min-width="160" />
        <el-table-column prop="quantity" label="数量" width="80" align="center" />
        <el-table-column prop="lab_name" label="所属实验室" min-width="150" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small" effect="plain">{{ row.status_text }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openDialog(row)">编辑</el-button>
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

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑设备' : '新增设备'" width="500px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="92px">
        <el-form-item label="所属实验室" prop="lab_id">
          <el-select v-model="form.lab_id" filterable placeholder="请选择实验室" style="width: 100%">
            <el-option v-for="lab in labs" :key="lab.id" :label="lab.name" :value="lab.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="设备名称" prop="name">
          <el-input v-model="form.name" placeholder="如：数字示波器" />
        </el-form-item>
        <el-form-item label="型号/规格" prop="model">
          <el-input v-model="form.model" placeholder="如：泰克 TBS1102B" />
        </el-form-item>
        <el-form-item label="数量" prop="quantity">
          <el-input-number v-model="form.quantity" :min="0" :max="10000" />
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-select v-model="form.status" style="width: 100%">
            <el-option label="正常" value="normal" />
            <el-option label="维修中" value="repair" />
            <el-option label="已报废" value="scrapped" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { equipmentApi, labApi } from '@/api'

const loading = ref(false)
const saving = ref(false)
const list = ref([])
const total = ref(0)
const labs = ref([])

const query = reactive({ page: 1, page_size: 10, keyword: '', lab_id: null, status: '' })

const dialogVisible = ref(false)
const formRef = ref()
const form = reactive({ id: null, lab_id: null, name: '', model: '', quantity: 1, status: 'normal', description: '' })
const rules = {
  lab_id: [{ required: true, message: '请选择所属实验室', trigger: 'change' }],
  name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }],
}

function statusType(status) {
  return { normal: 'success', repair: 'warning', scrapped: 'info' }[status] || 'info'
}

async function load() {
  loading.value = true
  try {
    const { data } = await equipmentApi.list({ ...query, lab_id: query.lab_id || undefined })
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
  Object.assign(query, { page: 1, keyword: '', lab_id: null, status: '' })
  load()
}

function openDialog(row) {
  form.id = row?.id || null
  Object.assign(form, {
    lab_id: row?.lab_id ?? null, name: row?.name || '', model: row?.model || '',
    quantity: row?.quantity ?? 1, status: row?.status || 'normal', description: row?.description || '',
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
      await equipmentApi.update(form.id, payload)
      ElMessage.success('修改成功')
    } else {
      await equipmentApi.create(payload)
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
    await ElMessageBox.confirm(`确定删除设备「${row.name}」吗？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  await equipmentApi.remove(row.id)
  ElMessage.success('删除成功')
  load()
}

onMounted(async () => {
  const { data } = await labApi.all()
  labs.value = data.list || []
  load()
})
</script>

<style scoped>
.flex-spacer {
  flex: 1;
}
</style>
