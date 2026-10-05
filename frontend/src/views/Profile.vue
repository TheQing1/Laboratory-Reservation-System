<template>
  <div class="page-container">
    <el-row :gutter="14">
      <el-col :xs="24" :lg="9">
        <el-card shadow="never" class="mb14">
          <div class="profile-head">
            <el-upload
              class="avatar-upload"
              :show-file-list="false"
              :before-upload="beforeAvatarUpload"
              :http-request="uploadAvatar"
              accept="image/*"
            >
              <el-avatar :size="82" :src="form.avatar || ''">
                {{ displayName.charAt(0) }}
              </el-avatar>
              <div class="avatar-tip">点击更换头像</div>
            </el-upload>
            <div class="profile-name">{{ displayName }}</div>
            <el-tag :type="userStore.isAdmin ? 'danger' : 'success'" effect="plain">
              {{ userStore.user?.role_text }}
            </el-tag>
            <div class="profile-username">@{{ userStore.user?.username }}</div>
          </div>
          <el-divider />
          <div class="info-list">
            <div class="info-row"><span>学号</span><b>{{ form.student_no || '—' }}</b></div>
            <div class="info-row"><span>学院</span><b>{{ form.college || '—' }}</b></div>
            <div class="info-row"><span>手机号</span><b>{{ form.phone || '—' }}</b></div>
            <div class="info-row"><span>邮箱</span><b>{{ form.email || '—' }}</b></div>
            <div class="info-row">
              <span>注册时间</span><b>{{ formatDate(userStore.user?.created_at) }}</b>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="15">
        <el-card shadow="never" class="mb14">
          <div class="card-title">基本资料</div>
          <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
            <el-form-item label="姓名" prop="name">
              <el-input v-model="form.name" />
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
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="saveProfile">保存修改</el-button>
              <el-button @click="resetForm">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="never">
          <div class="card-title">修改密码</div>
          <el-form ref="pwdRef" :model="pwdForm" :rules="pwdRules" label-width="90px">
            <el-form-item label="原密码" prop="old_password">
              <el-input v-model="pwdForm.old_password" type="password" show-password />
            </el-form-item>
            <el-form-item label="新密码" prop="new_password">
              <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="至少 6 位" />
            </el-form-item>
            <el-form-item label="确认密码" prop="confirm">
              <el-input v-model="pwdForm.confirm" type="password" show-password />
            </el-form-item>
            <el-form-item>
              <el-button type="warning" :loading="pwdSaving" @click="savePassword">确认修改</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { uploadApi, userApi } from '@/api'
import { useUserStore } from '@/store/user'

const router = useRouter()
const userStore = useUserStore()

const formRef = ref()
const pwdRef = ref()
const saving = ref(false)
const pwdSaving = ref(false)

const displayName = computed(() => userStore.displayName)

const form = reactive({ name: '', student_no: '', college: '', phone: '', email: '', avatar: '' })

const rules = {
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  email: [{ type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
  phone: [{ pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确', trigger: 'blur' }],
}

const pwdForm = reactive({ old_password: '', new_password: '', confirm: '' })
const pwdRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_r, v, cb) => (v === pwdForm.new_password ? cb() : cb(new Error('两次输入的密码不一致'))),
      trigger: 'blur',
    },
  ],
}

function formatDate(t) {
  if (!t) return '—'
  return String(t).replace('T', ' ').slice(0, 10)
}

function syncForm() {
  const u = userStore.user || {}
  Object.assign(form, {
    name: u.name || '',
    student_no: u.student_no || '',
    college: u.college || '',
    phone: u.phone || '',
    email: u.email || '',
    avatar: u.avatar || '',
  })
}

function resetForm() {
  syncForm()
  formRef.value?.clearValidate()
}

async function saveProfile() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const { data } = await userApi.updateProfile({ ...form })
    userStore.setUser(data)
    ElMessage.success('资料已更新')
  } catch {
    // 已提示
  } finally {
    saving.value = false
  }
}

async function savePassword() {
  try {
    await pwdRef.value.validate()
  } catch {
    return
  }
  pwdSaving.value = true
  try {
    await userApi.changePassword({
      old_password: pwdForm.old_password,
      new_password: pwdForm.new_password,
    })
    ElMessage.success('密码修改成功，请重新登录')
    setTimeout(async () => {
      await userStore.logout()
      router.push('/login')
    }, 800)
  } catch {
    // 已提示
  } finally {
    pwdSaving.value = false
  }
}

function beforeAvatarUpload(file) {
  const isImage = file.type.startsWith('image/')
  const okSize = file.size / 1024 / 1024 < 5
  if (!isImage) {
    ElMessage.error('只能上传图片文件')
    return false
  }
  if (!okSize) {
    ElMessage.error('图片大小不能超过 5MB')
    return false
  }
  return true
}

async function uploadAvatar({ file }) {
  try {
    const { data } = await uploadApi.image(file)
    const { data: updated } = await userApi.updateProfile({ ...form, avatar: data.url })
    userStore.setUser(updated)
    form.avatar = data.url
    ElMessage.success('头像已更新')
  } catch {
    // 已提示
  }
}

onMounted(syncForm)
</script>

<style scoped>
.mb14 {
  margin-bottom: 14px;
  border: none;
}

.profile-head {
  text-align: center;
  padding: 10px 0;
}

.avatar-upload {
  display: inline-block;
  cursor: pointer;
}

.avatar-upload :deep(.el-upload) {
  display: block;
}

.avatar-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 6px;
}

.profile-name {
  font-size: 18px;
  font-weight: 600;
  color: #1f2d3d;
  margin: 10px 0 6px;
}

.profile-username {
  font-size: 12px;
  color: #a8abb2;
  margin-top: 6px;
}

.info-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: #606266;
}

.info-row b {
  color: #303133;
  font-weight: 500;
}
</style>
