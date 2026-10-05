import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: [
      // 子路径的 CJS 产物无法作为 ESM 使用；指向自带 ESM 构建。
      // Element Plus 用带 .js 的写法（dayjs/plugin/x.js），ESM 侧是目录结构。
      {
        find: /^dayjs\/plugin\/(.+)\.js$/,
        replacement: fileURLToPath(new URL('./node_modules/dayjs/esm/plugin/', import.meta.url)) + '$1/index.js',
      },
      {
        find: /^dayjs\/plugin\/(.+)$/,
        replacement: fileURLToPath(new URL('./node_modules/dayjs/esm/plugin/', import.meta.url)) + '$1/index.js',
      },
      {
        find: /^dayjs\/locale\/(.+?)\.js$/,
        replacement: fileURLToPath(new URL('./node_modules/dayjs/esm/locale/', import.meta.url)) + '$1.js',
      },
      {
        find: /^dayjs\/locale\/(.+)$/,
        replacement: fileURLToPath(new URL('./node_modules/dayjs/esm/locale/', import.meta.url)) + '$1',
      },
      {
        find: /^dayjs$/,
        replacement: fileURLToPath(new URL('./node_modules/dayjs/esm/index.js', import.meta.url)),
      },
      { find: '@', replacement: fileURLToPath(new URL('./src', import.meta.url)) },
    ],
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: false,
    proxy: {
      // 后端 FastAPI 服务
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // 上传的静态资源
      '/uploads': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
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
})
