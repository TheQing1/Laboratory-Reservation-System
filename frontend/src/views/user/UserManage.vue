<template>
  <div class="page-container">
    <el-card shadow="never">
      <div class="card-title">
        用户管理
        <span class="sub">共 {{ total }} 个账号</span>
      </div>

      <div class="search-bar">
        <el-input
          v-model="query.keyword"
          placeholder="搜索用户名/姓名/学号/邮箱"
          :prefix-icon="Search"
          clearable
          style="width: 250px"
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-select v-model="query.role" placeholder="全部角色" clearable style="width: 130px" @change="reload">
          <el-option label="管理员" value="admin" />
          <el-option label="学生" value="student" />
        </el-select>
        <el-select v-model="query.is_active" placeholder="全部状态" clearable style="width: 130px" @change="reload">
          <el-option label="已启用" :value="true" />
          <el-option label="已禁用" :value="false" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="reload">查询</el-button>
        <el-button :icon="Refresh" @click="reset">重置</el-button>
        <div class="flex-spacer" />
        <el-button type="primary" :icon="Plus" @click="openDialog()">新增用户</el-button>
      </div>

      <el-table :data="list" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="用户" min-width="180">
          <template #default="{ row }">
            <div class="user-cell">
              <el-avatar :size="30" :src="row.avatar || ''">{{ (row.name || row.username).charAt(0) }}</el-avatar>
              <div>
                <div class="u-name">{{ row.name || row.username }}</div>
                <div class="u-sub">@{{ row.username }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'success'" size="small" effect="plain">
              {{ row.role_text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="student_no" label="学号" width="130" />
        <el-table-column prop="college" label="学院" min-width="140" />
        <el-table-column prop="phone" label="手机号" width="130" />
        <el-table-column prop="email" label="邮箱" min-width="170" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small" effect="plain">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openDialog(row)">编辑</el-button>
            <el-button
              size="small"
              link
              :type="row.is_active ? 'warning' : 'success'"
              @click="toggle(row)"
            >
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
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

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑用户' : '新增用户'" width="560px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="92px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :disabled="!!form.id" placeholder="登录账号" />
        </el-form-item>
        <el-form-item v-if="!form.id" label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="姓名" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-radio-group v-model="form.role">
            <el-radio value="student">学生</el-radio>
            <el-radio value="admin">管理员</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-row :gutter="10">
          <el-col :span="12">
            <el-form-item label="学号" prop="student_no">
              <el-input v-model="form.student_no" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="学院" prop="college">
              <el-input v-model="form.college" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="10">
          <el-col :span="12">
            <el-form-item label="手机号" prop="phone">
              <el-input v-model="form.phone" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="form.email" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="状态" prop="is_active">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
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
import { userApi } from '@/api'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const loading = ref(false)
const saving = ref(false)
const list = ref([])
const total = ref(0)

const query = reactive({ page: 1, page_size: 10, keyword: '', role: '', is_active: null })

const dialogVisible = ref(false)
const formRef = ref()
const form = reactive({
  id: null, username: '', password: '', name: '', role: 'student',
  student_no: '', college: '', phone: '', email: '', is_active: true,
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, min: 6, message: '密码至少 6 位', trigger: 'blur' }],
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  email: [{ type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
  phone: [{ pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确', trigger: 'blur' }],
}

async function load() {
  loading.value = true
  try {
    const params = { ...query }
    if (params.is_active === null) delete params.is_active
    const { data } = await userApi.list(params)
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
  Object.assign(query, { page: 1, keyword: '', role: '', is_active: null })
  load()
}

function openDialog(row) {
  form.id = row?.id || null
  Object.assign(form, {
    username: row?.username || '', password: '', name: row?.name || '', role: row?.role || 'student',
    student_no: row?.student_no || '', college: row?.college || '', phone: row?.phone || '',
    email: row?.email || '', is_active: row?.is_active ?? true,
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
    if (form.id) {
      const payload = { ...form }
      delete payload.id
      delete payload.username
      delete payload.password
      await userApi.update(form.id, payload)
      ElMessage.success('修改成功')
    } else {
      const payload = { ...form }
      delete payload.id
      await userApi.create(payload)
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

async function toggle(row) {
  if (row.id === userStore.user?.id) {
    ElMessage.warning('不能禁用当前登录的账号')
    return
  }
  await userApi.toggleStatus(row.id, !row.is_active)
  ElMessage.success(row.is_active ? '已禁用' : '已启用')
  load()
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除用户「${row.name || row.username}」吗？其预约记录也会一并删除。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
    })
  } catch {
    return
  }
  try {
    await userApi.remove(row.id)
    ElMessage.success('删除成功')
    load()
  } catch {
    // 已提示
  }
}

onMounted(load)
</script>

<style scoped>
.flex-spacer {
  flex: 1;
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.u-name {
  font-size: 14px;
  color: #303133;
}

.u-sub {
  font-size: 12px;
  color: #a8abb2;
}
</style>
