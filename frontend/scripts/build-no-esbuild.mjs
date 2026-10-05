/**
 * 构建脚本（沙箱友好 + 生产可用）
 *
 * 背景：Vite 默认用 esbuild 转译 JS/TS 并压缩产物。当前环境的沙箱禁止
 * Node 以管道方式创建子进程，esbuild 的 service 进程无法启动（spawn EPERM）。
 *
 * 本项目源码全部是标准 JavaScript（无 TS/JSX/装饰器），Babel 的 esbuild
 * 用法也不需要，因此可以安全地关闭 esbuild：
 *   - esbuild: false      -> 跳过 esbuild 转译
 *   - build.minify: false -> 跳过 esbuild 压缩（改用 Rollup 打包）
 *
 * 依赖预打包（optimizeDeps）同样会调用 esbuild，所以构建时设为关闭；
 * dev 模式请使用 scripts/dev-esbuild-off.mjs。
 */
import { build } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, pathToFileURL, URL } from 'node:url'
import { rm } from 'node:fs/promises'

const root = fileURLToPath(new URL('..', import.meta.url))

// 内联配置：避免 Vite 为加载 vite.config.js 而调用 esbuild 打包配置文件
const config = {
  root,
  configFile: false,
  mode: 'production',
  logLevel: 'info',
  esbuild: false,
  plugins: [vue()],
  // 等价于 Vite 默认注入的 Vue 特性开关（见 vite 的 resolveConfig）。
  // 注意：必须放在顶层 define，Vite 的 define 插件才会实际替换并消除运行时警告。
  define: {
    __VUE_OPTIONS_API__: true,
    __VUE_PROD_DEVTOOLS__: false,
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: false,
  },
  resolve: {
    alias: [
      // 同 dev 脚本：dayjs 及其 plugin/locale 子路径的 CJS 产物在浏览器中无法作为
      // ESM 使用，统一指向其自带 ESM 构建。
      // Element Plus 使用带 .js 扩展名的写法，ESM 侧是目录结构，需要去掉 .js。
      {
        find: /^dayjs\/plugin\/(.+)\.js$/,
        replacement: fileURLToPath(new URL('../node_modules/dayjs/esm/plugin/', import.meta.url)) + '$1/index.js',
      },
      {
        find: /^dayjs\/plugin\/(.+)$/,
        replacement: fileURLToPath(new URL('../node_modules/dayjs/esm/plugin/', import.meta.url)) + '$1/index.js',
      },
      {
        find: /^dayjs\/locale\/(.+?)\.js$/,
        replacement: fileURLToPath(new URL('../node_modules/dayjs/esm/locale/', import.meta.url)) + '$1.js',
      },
      {
        find: /^dayjs\/locale\/(.+)$/,
        replacement: fileURLToPath(new URL('../node_modules/dayjs/esm/locale/', import.meta.url)) + '$1',
      },
      {
        find: /^dayjs$/,
        replacement: fileURLToPath(new URL('../node_modules/dayjs/esm/index.js', import.meta.url)),
      },
      { find: '@', replacement: fileURLToPath(new URL('../src', import.meta.url)) },
    ],
  },
  optimizeDeps: { noDiscovery: true, include: [] },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    minify: false, // 交给 Rollup，避免 esbuild
    chunkSizeWarningLimit: 4000,
    rollupOptions: {
      output: {
        manualChunks: {
          vue: ['vue', 'vue-router', 'pinia'],
          element: ['element-plus', '@element-plus/icons-vue'],
          charts: ['echarts'],
        },
      },
    },
  },
}

export async function buildNoEsbuild() {
  await rm(new URL('../dist', import.meta.url), { recursive: true, force: true })
  await build(config)
  console.log('\n✅ 构建完成：frontend/dist（无 esbuild 模式）')
}

// 直接执行 `node scripts/build-no-esbuild.mjs` 时才运行；被 build.mjs 导入时只导出函数
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await buildNoEsbuild()
}
