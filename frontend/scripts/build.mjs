/**
 * 生产构建入口（与 `npm run build` 绑定）
 *
 * 策略：优先使用标准 Vite（走 vite.config.js，含 esbuild 转译与压缩）；
 * 若当前环境禁止 esbuild 工作（受限沙箱常见的 EPERM / Access is denied），
 * 自动降级为 scripts/build-no-esbuild.mjs，保证任何环境下都能产出可运行的 dist。
 *
 * 想强制走某条路径时：
 *   npm run build:standard   # 只用标准 Vite
 *   npm run build:sandbox    # 只用无 esbuild 构建
 */
import { build } from 'vite'
import { fileURLToPath, URL } from 'node:url'
import { rm } from 'node:fs/promises'

function isRestrictedEnvError(err) {
  const text = String((err && (err.stack || err.message)) || err)
  return /esbuild/i.test(text) && /(EPERM|EACCES|Access is denied|spawn)/i.test(text)
}

const root = fileURLToPath(new URL('..', import.meta.url))
const configFile = fileURLToPath(new URL('../vite.config.js', import.meta.url))

try {
  await rm(new URL('../dist', import.meta.url), { recursive: true, force: true })
  await build({ root, configFile, mode: 'production' })
  console.log('\n✅ 构建完成（标准 Vite）：frontend/dist')
} catch (err) {
  if (!isRestrictedEnvError(err)) throw err
  console.warn('\n⚠ 检测到受限环境（esbuild 不可用），自动切换为无 esbuild 构建…')
  const { buildNoEsbuild } = await import('./build-no-esbuild.mjs')
  await buildNoEsbuild()
}
