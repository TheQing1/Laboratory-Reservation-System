# 开发与构建说明

本文档收录 README 里放不下的工程细节，主要是**前端构建在受限环境下的处理**。
如果你在普通开发机上，下面绝大部分内容可以忽略。

---

## 一、后端

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- 数据库默认 SQLite（`backend/data/lab_booking.db`），首次启动自动建表并写入演示数据。
- SQLite 连接已开启 `foreign_keys`、`journal_mode=WAL` 与 `busy_timeout`，降低并发写入时的锁冲突。
- 启动时会执行一次 `services.sync_slot_index()`，把 `reservation_slots` 与现有有效预约对齐，兼容旧数据。
- 建表使用 `Base.metadata.create_all`（无迁移工具）。切换 MySQL 时先把
  `DATABASE_URL` 改成 `mysql+pymysql://...` 并 `pip install pymysql` 即可。

### 环境变量

见 `backend/.env.example`。几个需要注意的点：

- `SECRET_KEY`：默认值仅供本地开发。`DEBUG=false` 且仍使用默认/占位密钥时，服务会**拒绝启动**。
- `CORS_ORIGINS`：开发期可用 `*`，上线请收敛为实际域名（逗号分隔）。
- `LLM_API_KEY`：不填则走本地助手引擎，功能不缺失。
- `EMBEDDING_API_KEY`：不填则使用内置离线哈希向量，无需下载模型。

---

## 二、前端

```bash
cd frontend
npm install
npm run dev            # 开发服务器（受限环境友好）
npm run build          # 生产构建（自动选择标准 / 无 esbuild）
```

### 脚本一览

| 命令 | 说明 |
|------|------|
| `npm run dev` | 开发服务器，关闭 esbuild 与依赖预打包，任何环境都能启动 |
| `npm run dev:standard` | 标准 Vite 开发服务器（普通环境冷启动更快） |
| `npm run build` | 生产构建：先尝试标准 Vite，失败且判定为受限环境时自动降级 |
| `npm run build:standard` | 只用标准 Vite（含 esbuild 压缩） |
| `npm run build:sandbox` | 只用无 esbuild 构建（关闭压缩，交给 Rollup） |
| `npm run preview` | 预览构建产物（端口 5174） |

`scripts/build.mjs` 的降级判定是：错误信息同时命中 `esbuild` 与
`EPERM / EACCES / Access is denied / spawn`。只有这种“环境不允许 esbuild 工作”的错误才会降级，
真正的代码错误会照常抛出，不会被吞掉。

### 构建产物校验

```bash
cd frontend
npm run build
node scripts/verify-bundle.cjs     # 产物：process.env 残留、裸模块、页面 chunk、样式文件
node scripts/verify-devgraph.mjs   # 需先启动 dev 服务：递归解析整个模块图，查 404 与 CJS 依赖
```

`verify-bundle.cjs` 能提前发现“构建成功但浏览器白屏”这类问题（例如 `process.env.NODE_ENV` 未被替换）。

---

## 三、受限环境（沙箱）下为什么需要特殊处理

### 1. Vite 的两处补丁

`scripts/patch-vite.mjs` 会幂等地修改 `node_modules/vite` 产物，解决两个问题：

1. **`net use` 探测**：Vite 的 `optimizeSafeRealPathSync()` 会执行 `exec("net use")` 识别 Windows
   网络驱动器；在禁止创建子进程的环境里会**同步抛出 `spawn EPERM`**，且发生在 Rollup 的 `resolveId`
   钩子内，外部无法捕获。补丁改为直接使用 `fs.realpathSync.native`（无网络驱动器映射时本就是这条分支，语义等价）。
2. **`vite:define` 插件**：该插件无条件调用 `esbuild.transform` 做常量替换，不受 `config.esbuild = false`
   控制。补丁改为“成员访问级”的纯文本替换，保证 `process.env.NODE_ENV` 等被真正替换掉——
   否则浏览器里没有 `process`，页面会直接白屏。

> 补丁是幂等的；升级或重装 Vite 后重新执行即可。普通环境不需要这些补丁，
> 直接用 `npm run build:standard` / `npm run dev:standard`。

### 2. dayjs 的 ESM 别名

`dayjs` 的 `package.json` 只有 `main: dayjs.min.js`（UMD），没有 `module` 字段，
而 Element Plus 以 `import dayjs from "dayjs"` 和
`import customParseFormat from "dayjs/plugin/customParseFormat.js"` 引用它。
正常情况下这由 Vite 的 esbuild 预打包转换；关闭 esbuild 后必须显式指向 dayjs 自带的 ESM 构建：

- CJS 侧是 `plugin/<name>.js`（单文件），ESM 侧是 `plugin/<name>/index.js`（目录）；
- Element Plus 会带 `.js` 后缀，别名规则必须把这层差异处理掉。

`vite.config.js` 与两个 no-esbuild 脚本里都维护了同一组别名，二者需要保持一致。

---

## 四、测试

```bash
# 后端接口冒烟测试（需先启动后端）：60 项断言，含并发抢约与数据还原
cd backend && node scripts/smoke-test.mjs

# 前端构建产物校验
cd frontend && npm run build && node scripts/verify-bundle.cjs
```

冒烟测试会创建/删除临时实验室、设备、文档与预约，并临时修改学生资料后**自动还原**。
它依赖演示种子数据（8 间实验室、11 篇文档），因此请在未大改种子数据的情况下运行。
