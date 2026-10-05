/**
 * 开发服务器（沙箱友好）
 *
 * 与 build-no-esbuild.mjs 同样的思路：关闭 esbuild 与依赖预打包，
 * 由 Vite 直接用 @vue/compiler-sfc 编译 .vue、原样提供 JS 模块。
 *
 * 如果你的环境可以正常创建子进程，直接 `npm run dev`（标准 Vite）即可，
 * 依赖预打包会带来更快的冷启动。
 */
import { createServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))

const server = await createServer({
  root,
  configFile: false,
  mode: 'development',
  esbuild: false,
  plugins: [vue()],
  // 与生产构建保持一致，避免 Vue 运行时特性开关警告
  define: {
    __VUE_OPTIONS_API__: true,
    __VUE_PROD_DEVTOOLS__: false,
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: false,
  },
  resolve: {
    alias: [
      // dayjs 的 "main" 与 plugin/locale 子路径都是 UMD/CJS（没有 ESM default 导出），
      // 而 Element Plus 以 `import dayjs from "dayjs"` / `import p from "dayjs/plugin/x"`
      // 方式引用它们。常规做法依赖 Vite 的 esbuild 预打包来转换；本环境无法运行
      // esbuild，因此统一指向 dayjs 自带的 ESM 构建。
      //
      // 注意目录结构差异：CJS 是 plugin/<name>.js，ESM 是 plugin/<name>/index.js。
      // 顺序很重要，长的前缀必须排在裸 "dayjs" 之前。
      // 注意：Element Plus 使用带扩展名的写法（dayjs/plugin/customParseFormat.js），
      // 而 ESM 侧是目录结构（plugin/<name>/index.js），因此这里要把 .js 去掉。
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
  // 依赖预打包会调用 esbuild，这里关闭
  optimizeDeps: { noDiscovery: true, include: [] },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/uploads': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})

await server.listen()
server.printUrls()
