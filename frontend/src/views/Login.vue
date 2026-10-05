<template>
  <div class="login-page">
    <!-- 左侧品牌区 -->
    <div class="brand">
      <div class="brand-inner">
        <div class="brand-logo">🔬</div>
        <h1>智能实验室预约系统</h1>
        <p class="slogan">FastAPI + Vue3 + AI Agent · 高校实验室一站式预约与管理平台</p>
        <ul class="features">
          <li><el-icon><Calendar /></el-icon> 在线预约实验室与设备，实时查看空闲时段</li>
          <li><el-icon><MagicStick /></el-icon> AI 智能助手对话式预约，自动查数据、代提交</li>
          <li><el-icon><Notebook /></el-icon> RAG 知识库问答，实验室规章安全随手可查</li>
          <li><el-icon><DataAnalysis /></el-icon> 预约审核与可视化统计，管理一目了然</li>
        </ul>
      </div>
    </div>

    <!-- 右侧表单区 -->
    <div class="form-area">
      <div class="form-card">
        <h2 class="form-title">欢迎回来 👋</h2>
        <p class="form-sub">请登录你的账号以继续使用</p>

        <el-form ref="formRef" :model="form" :rules="rules" size="large" @keyup.enter="onSubmit">
          <el-form-item prop="username">
            <el-input v-model="form.username" placeholder="请输入用户名" :prefix-icon="User" clearable />
          </el-form-item>
          <el-form-item prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              :prefix-icon="Lock"
              show-password
              clearable
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" class="submit-btn" :loading="loading" @click="onSubmit">
              登 录
            </el-button>
          </el-form-item>
        </el-form>

        <div class="demo-accounts">
          <div class="demo-title">演示账号（点击一键填充）</div>
          <div class="demo-list">
            <div class="demo-item" @click="fill('admin', 'admin123')">
              <el-tag type="danger" size="small" effect="plain">管理员</el-tag>
              <span>admin / admin123</span>
            </div>
            <div class="demo-item" @click="fill('student', 'student123')">
              <el-tag type="success" size="small" effect="plain">学生</el-tag>
              <span>student / student123</span>
            </div>
          </div>
        </div>

        <div class="form-footer">
          还没有账号？<el-link type="primary" @click="router.push('/register')">立即注册</el-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Calendar, DataAnalysis, Lock, MagicStick, Notebook, User } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const formRef = ref()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

function fill(username, password) {
  form.username = username
  form.password = password
}

async function onSubmit() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    const user = await userStore.login({ ...form })
    ElMessage.success(`登录成功，欢迎回来，${user.name || user.username}`)
    const redirect = route.query.redirect
    router.push(redirect && redirect !== '/' ? redirect : '/dashboard')
  } catch {
    // 错误提示已在拦截器统一处理
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.brand {
  flex: 1.15;
  background: linear-gradient(135deg, #1b3a6b 0%, #2b6cb0 55%, #409eff 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.brand::after {
  content: '';
  position: absolute;
  width: 620px;
  height: 620px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.06);
  right: -220px;
  bottom: -260px;
}

.brand-inner {
  position: relative;
  z-index: 1;
  max-width: 460px;
  padding: 40px;
}

.brand-logo {
  font-size: 54px;
  margin-bottom: 16px;
}

.brand h1 {
  font-size: 32px;
  margin: 0 0 12px;
  letter-spacing: 1px;
}

.slogan {
  font-size: 14px;
  opacity: 0.86;
  line-height: 1.7;
  margin-bottom: 32px;
}

.features {
  list-style: none;
  padding: 0;
  margin: 0;
}

.features li {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  padding: 10px 0;
  opacity: 0.94;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}

.form-area {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
}

.form-card {
  width: 360px;
  padding: 20px;
}

.form-title {
  font-size: 24px;
  margin: 0 0 6px;
  color: #1f2d3d;
}

.form-sub {
  color: #909399;
  font-size: 13px;
  margin: 0 0 26px;
}

.submit-btn {
  width: 100%;
  letter-spacing: 4px;
}

.demo-accounts {
  margin-top: 6px;
  background: #f7f9fc;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
  padding: 12px 14px;
}

.demo-title {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.demo-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.demo-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 4px;
  transition: background 0.2s;
}

.demo-item:hover {
  background: #ecf5ff;
}

.form-footer {
  margin-top: 20px;
  text-align: center;
  font-size: 13px;
  color: #909399;
}

@media (max-width: 900px) {
  .brand {
    display: none;
  }
}
</style>
