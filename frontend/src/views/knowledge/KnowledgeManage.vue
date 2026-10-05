<template>
  <div class="page-container">
    <el-row :gutter="14" class="mb14">
      <el-col :xs="12" :md="6">
        <el-card shadow="never" class="mini-card">
          <div class="mini-value">{{ stats.documents }}</div>
          <div class="mini-label">知识文档</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card shadow="never" class="mini-card">
          <div class="mini-value">{{ stats.chunks }}</div>
          <div class="mini-label">向量片段</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card shadow="never" class="mini-card">
          <div class="mini-value small">{{ stats.backend === 'remote' ? '远端模型' : '本地向量' }}</div>
          <div class="mini-label">向量化方式</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card shadow="never" class="mini-card">
          <div class="mini-value small">{{ stats.dim }} 维</div>
          <div class="mini-label">向量维度</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="14">
      <el-col :xs="24" :lg="15">
        <el-card shadow="never">
          <div class="card-title">
            知识库文档
            <div>
              <el-button size="small" :icon="Refresh" @click="reindex">重建索引</el-button>
              <el-button size="small" type="primary" :icon="Plus" @click="openDialog()">新增文档</el-button>
            </div>
          </div>

          <div class="search-bar">
            <el-input
              v-model="query.keyword"
              placeholder="搜索标题/内容"
              :prefix-icon="Search"
              clearable
              style="width: 230px"
              @keyup.enter="reload"
              @clear="reload"
            />
            <el-select v-model="query.category" placeholder="全部分类" clearable style="width: 150px" @change="reload">
              <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
            </el-select>
            <el-select v-model="query.lab_id" placeholder="全部实验室" clearable filterable style="width: 190px" @change="reload">
              <el-option v-for="lab in labs" :key="lab.id" :label="lab.name" :value="lab.id" />
            </el-select>
            <el-button type="primary" :icon="Search" @click="reload">查询</el-button>
          </div>

          <el-table :data="list" v-loading="loading" stripe>
            <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
            <el-table-column label="分类" width="110">
              <template #default="{ row }">
                <el-tag size="small" effect="plain" type="info">{{ row.category }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="关联实验室" width="150">
              <template #default="{ row }">
                <span :class="{ 'text-muted': !row.lab_name }">{{ row.lab_name || '通用' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="content_preview" label="内容预览" min-width="230" show-overflow-tooltip />
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
      </el-col>

      <el-col :xs="24" :lg="9">
        <el-card shadow="never">
          <div class="card-title">
            检索测试
            <span class="sub">验证 RAG 效果</span>
          </div>
          <el-input
            v-model="testQuery"
            placeholder="输入问题，如：实验室违规怎么处理"
            @keyup.enter="doSearch"
          >
            <template #append>
              <el-button :icon="Search" @click="doSearch">检索</el-button>
            </template>
          </el-input>

          <div v-if="hits.length" class="hit-list">
            <div v-for="(h, i) in hits" :key="i" class="hit">
              <div class="hit-head">
                <span class="hit-rank">{{ i + 1 }}</span>
                <span class="hit-title">{{ h.title }}</span>
                <el-tag size="small" effect="plain">相似度 {{ h.score }}</el-tag>
              </div>
              <div class="hit-body">{{ h.content }}</div>
            </div>
          </div>
          <el-empty v-else-if="searched" description="没有检索到相关内容" :image-size="60" />
          <div v-else class="hint-box">
            提示：这里展示的是 AI 助手回答制度类问题时实际依据的知识片段。
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑文档' : '新增文档'" width="640px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="如：实验室预约管理办法" />
        </el-form-item>
        <el-row :gutter="10">
          <el-col :span="12">
            <el-form-item label="分类" prop="category">
              <el-input v-model="form.category" placeholder="如：规章制度 / 安全规范" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="关联实验室" prop="lab_id">
              <el-select v-model="form.lab_id" placeholder="通用知识（留空）" clearable filterable style="width: 100%">
                <el-option v-for="lab in labs" :key="lab.id" :label="lab.name" :value="lab.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="内容" prop="content">
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="10"
            placeholder="粘贴或输入知识内容，保存后会自动切片并向量化"
          />
        </el-form-item>
        <el-form-item label="来源" prop="source">
          <el-input v-model="form.source" placeholder="选填，如：《实验室管理条例》第三章" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存并向量化</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { documentApi, labApi } from '@/api'

const loading = ref(false)
const saving = ref(false)
const list = ref([])
const total = ref(0)
const labs = ref([])
const categories = ref([])
const stats = reactive({ documents: 0, chunks: 0, backend: 'local', dim: 512 })

const query = reactive({ page: 1, page_size: 10, keyword: '', category: '', lab_id: null })

const testQuery = ref('')
const hits = ref([])
const searched = ref(false)

const dialogVisible = ref(false)
const formRef = ref()
const form = reactive({ id: null, title: '', category: '规章制度', content: '', source: '', lab_id: null })
const rules = {
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  content: [{ required: true, min: 10, message: '内容至少 10 个字符', trigger: 'blur' }],
}

async function load() {
  loading.value = true
  try {
    const { data } = await documentApi.list({ ...query, lab_id: query.lab_id || undefined })
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

async function loadMeta() {
  try {
    const [s, c, l] = await Promise.all([documentApi.stats(), documentApi.categories(), labApi.all()])
    Object.assign(stats, s.data)
    categories.value = c.data || []
    labs.value = l.data.list || []
  } catch {
    // 忽略
  }
}

function openDialog(row) {
  form.id = row?.id || null
  Object.assign(form, {
    title: row?.title || '',
    category: row?.category || '规章制度',
    content: row?.content || '',
    source: row?.source || '',
    lab_id: row?.lab_id ?? null,
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
      await documentApi.update(form.id, payload)
      ElMessage.success('已保存并重新建立索引')
    } else {
      const { data } = await documentApi.create(payload)
      ElMessage.success(`已保存，生成 ${data.chunks} 个知识片段`)
    }
    dialogVisible.value = false
    load()
    loadMeta()
  } catch {
    // 已提示
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除文档「${row.title}」吗？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  await documentApi.remove(row.id)
  ElMessage.success('已删除')
  load()
  loadMeta()
}

async function reindex() {
  const { data } = await documentApi.reindex()
  ElMessage.success(`索引重建完成，共 ${data.chunks} 个片段`)
  loadMeta()
}

async function doSearch() {
  if (!testQuery.value.trim()) {
    ElMessage.warning('请输入检索内容')
    return
  }
  const { data } = await documentApi.search(testQuery.value.trim(), 3)
  hits.value = data || []
  searched.value = true
}

onMounted(() => {
  load()
  loadMeta()
})
</script>

<style scoped>
.mb14 {
  margin-bottom: 14px;
}

.mini-card {
  border: none;
  text-align: center;
}

.mini-value {
  font-size: 24px;
  font-weight: 700;
  color: #409eff;
}

.mini-value.small {
  font-size: 17px;
  line-height: 32px;
}

.mini-label {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

.hit-list {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 560px;
  overflow-y: auto;
}

.hit {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 10px 12px;
  background: #fafbfc;
}

.hit-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.hit-rank {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.hit-title {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: #1f2d3d;
}

.hit-body {
  font-size: 12px;
  color: #606266;
  line-height: 1.7;
}

.hint-box {
  margin-top: 12px;
  padding: 10px 12px;
  background: #f4faff;
  border: 1px dashed #c6e2ff;
  border-radius: 6px;
  font-size: 12px;
  color: #6b7785;
  line-height: 1.7;
}
</style>
