/**
 * 修复 Vite 在受限环境（沙箱）下的启动/构建失败。
 *
 * 问题：
 *   Vite 打包产物中的 optimizeSafeRealPathSync() 会执行
 *       exec("net use", callback)
 *   用于识别 Windows 网络驱动器映射。当进程创建被限制（沙箱禁止以管道方式
 *   创建子进程）时，child_process.exec 会「同步」抛出 spawn EPERM，
 *   该异常发生在 Rollup 的 resolveId 钩子内，外部无法捕获，导致：
 *       [commonjs--resolver] spawn EPERM   →  构建/启动直接失败
 *
 * 修复：
 *   直接把这次探测替换为 fs.realpathSync.native()。
 *   语义等价——在没有网络驱动器映射的机器上，Vite 原本就会走这条分支
 *   （见源码：windowsNetworkMap.size === 0 时 safeRealpathSync = realpathSync.native）。
 *
 * 幂等：已打过补丁的产物不会重复修改。若升级/重装 Vite，重新执行本脚本即可。
 */
import { readFile, writeFile } from 'node:fs/promises'
import { readdirSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))
const chunksDir = path.join(root, 'node_modules', 'vite', 'dist', 'node', 'chunks')

if (!existsSync(chunksDir)) {
  console.error('✗ 未找到 vite 产物目录，请先执行 npm install')
  process.exit(1)
}

const TARGET = `  exec("net use", (error, stdout) => {
    if (error) return;
    const lines = stdout.split("\\n");
    for (const line of lines) {
      const m = parseNetUseRE.exec(line);
      if (m) windowsNetworkMap.set(m[2], m[1]);
    }
    if (windowsNetworkMap.size === 0) {
      safeRealpathSync = fs__default.realpathSync.native;
    } else {
      safeRealpathSync = windowsMappedRealpathSync;
    }
  });`

const REPLACEMENT = `  // [patched by scripts/patch-vite.mjs] 受限环境无法 exec("net use")，
  // 本机无网络驱动器映射，直接使用原生 realpath（与原分支语义一致）。
  safeRealpathSync = fs__default.realpathSync.native;`

const files = readdirSync(chunksDir).filter((f) => f.endsWith('.js'))
let patched = 0
let already = 0

/**
 * 补丁二：vite:define 插件
 * 该插件无条件调用 esbuild.transform 做常量替换（不受 config.esbuild=false 控制）。
 * 受限环境无法调用 esbuild，因此改为「纯文本替换」实现同等效果。
 *
 * 关键点：
 *   1. 必须真正完成替换。Vue / Element Plus / ECharts 产物里含
 *      `process.env.NODE_ENV`，浏览器中没有 process，不替换会导致
 *      应用一加载就抛 `process is not defined`（白屏）。
 *   2. 必须只替换「完整的成员访问」，不能用朴素 split/join：
 *      Vite 还会定义 `process.env` 本身，且源码中存在
 *      `getGlobalThis()[__DEV__]` 这类动态成员访问，朴素替换会把
 *      `__DEV__` 换成 "true" 从而产生非法语法
 *      （如 `getGlobalThis()."true" = true`）。
 */
const DEFINE_TARGET = `async function replaceDefine(code, id, define, config) {
  const esbuildOptions = config.esbuild || {};`

const DEFINE_REPLACEMENT = `async function replaceDefine(code, id, define, config) {
  // [patched by scripts/patch-vite.mjs] 用「成员访问级」文本替换代替 esbuild.transform。
  {
    let out = code;
    const keys = Object.keys(define || {}).sort((a, b) => b.length - a.length);
    for (const key of keys) {
      const value = JSON.stringify(define[key]);
      // 匹配两种形式：普通标识符（__VUE_OPTIONS_API__）与成员访问（process.env.NODE_ENV）。
      // 左边界排除标识符字符与引号/模板串，右边界排除标识符字符与 '.'，
      // 避免把 process.env 误替换进 process.env.NODE_ENV、或替换字符串里的同名文字。
      if (/^(?:[A-Za-z_$][\\w$]*)(?:\\.[A-Za-z_$][\\w$]*)*$/.test(key)) {
        const dots = new RegExp('\\\\.', 'g');
        const pattern = new RegExp('(^|[^\\\\w$.' + '\\x27\\x22\\x60' + '])' + key.replace(dots, '\\\\.') + '(?![\\\\w$.])', 'g');
        out = out.replace(pattern, (m, p1) => p1 + value);
      }
    }
    return { code: out, map: null };
  }
  // eslint-disable-next-line no-unreachable
  const esbuildOptions = config.esbuild || {};`

async function applyPatch(file, source, target, replacement, label) {
  if (source.includes(replacement.slice(0, 60)) && label === 'define') return 'already'
  if (!source.includes(target)) return 'nomatch'
  await writeFile(file, source.replace(target, replacement), 'utf8')
  return 'patched'
}

for (const name of files) {
  const file = path.join(chunksDir, name)
  let source = await readFile(file, 'utf8')
  const original = source

  // 补丁一：Windows 网络驱动器 realpath 探测
  if (source.includes(TARGET)) {
    source = source.replace(TARGET, REPLACEMENT)
    patched++
    console.log(`✓ 已修补 ${name}（realpath）`)
  } else if (source.includes('[patched by scripts/patch-vite.mjs]')) {
    already++
  }

  // 补丁二：vite:define
  const defineState = await applyPatch(file, source, DEFINE_TARGET, DEFINE_REPLACEMENT, 'define')
  if (defineState === 'patched') {
    source = source.replace(DEFINE_TARGET, DEFINE_REPLACEMENT)
    patched++
    console.log(`✓ 已修补 ${name}（define）`)
  } else if (defineState === 'already') {
    already++
  }

  if (source !== original) {
    await writeFile(file, source, 'utf8')
  }
}

if (patched === 0 && already === 0) {
  console.warn('⚠ 未匹配到目标代码，Vite 版本可能已变化；如构建报 spawn EPERM，请检查本脚本。')
} else if (patched === 0) {
  console.log('✓ 补丁已存在，无需重复修改')
} else {
  console.log(`\n✅ Vite 补丁完成（${patched} 处）`)
}
