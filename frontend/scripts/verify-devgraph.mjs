/**
 * 浏览器模块图校验（针对「依赖预打包关闭」的环境）
 *
 * 运行：先启动 dev 服务，然后 node scripts/verify-devgraph.mjs
 *
 * 背景：受限环境无法运行 esbuild，Vite 的依赖预打包被关闭，
 * 浏览器直接加载 node_modules 里的原始文件。若某个依赖是 CommonJS/UMD
 * （例如 dayjs 的 main 指向 dayjs.min.js），就会在浏览器里报：
 *   Uncaught SyntaxError: The requested module '...' does not provide an export named 'default'
 * 这类错误只在浏览器运行时出现，构建成功并不代表没问颖，因此单独做一次图遍历校验。
 *
 * 检查项：
 *   1. 从 src/main.js 出发，递归跟进所有 import / export-from / 动态 import；
 *   2. 每个说明符都能被 dev 服务解析为 200（否则报 404）——**硬失败**；
 *   3. 目标模块若是 CJS/UMD（无任何 ESM 导出）却被当 ESM 导入 —— **硬失败**
 *      （这正是 dayjs 那个白屏问题的特征）；
 *   4. 具名/默认导出是否齐全 —— 仅作为**警告**输出。
 *      说明：这里是基于正则的静态近似，「默认导入」与「具名导入」的区分
 *      在复杂写法（import { x } / export { default as y } / 星号转发）下会出现误报，
 *      例如 echarts 大量使用无 default 的具名导出，会被误判。
 *      因此不把第 4 项作为失败条件，只用于提示人工复核。
 */
const BASE = process.env.BASE || 'http://127.0.0.1:5173'
const ENTRY = '/src/main.js'

const cache = new Map()
const hardProblems = []
const warnings = []
let checked = 0

function resolveSpec(spec, importerUrl) {
  if (spec.startsWith('http')) return spec
  if (spec.startsWith('/')) return BASE + spec
  return new URL(spec, importerUrl).href
}

/** 提取导入说明符及其绑定的名字 */
function extractImports(code) {
  const out = []
  // import d from 'x' / import d, {a, b as c} from 'x' / import * as ns from 'x'
  const reFrom = /import\s+([^'"]*?)\s*from\s*['"]([^'"]+)['"]/g
  let m
  while ((m = reFrom.exec(code))) {
    const clause = m[1].trim()
    const spec = m[2]
    const names = { default: false, namespace: false, named: [] }
    if (clause.startsWith('*')) names.namespace = true
    else {
      const [defPart, namedPart] = clause.split(/,(.+)/).map((s) => (s || '').trim())
      if (defPart && !defPart.startsWith('{')) names.default = true
      const braces = namedPart || (defPart?.startsWith('{') ? defPart : '')
      if (braces?.startsWith('{')) {
        for (const piece of braces.replace(/[{}]/g, '').split(',')) {
          const parts = piece.trim().split(/\s+as\s+/)
          const name = parts[0].trim()
          if (!name) continue
          // `import { default as x }` 等价于默认导入
          if (name === 'default') names.default = true
          else names.named.push(name)
        }
      }
    }
    out.push({ spec, names, kind: 'static' })
  }
  // 副作用导入 import 'x'
  const reSide = /(?:^|[\s;])import\s*['"]([^'"]+)['"]/g
  while ((m = reSide.exec(code))) out.push({ spec: m[1], names: null, kind: 'side' })
  // 动态导入 import('x')
  const reDyn = /import\s*\(\s*['"]([^'"]+)['"]\s*\)/g
  while ((m = reDyn.exec(code))) out.push({ spec: m[1], names: null, kind: 'dynamic' })
  // export ... from 'x'
  const reExport = /export\s+([^'"]*?)\s*from\s*['"]([^'"]+)['"]/g
  while ((m = reExport.exec(code))) {
    const clause = m[1].trim()
    const named = clause.startsWith('{')
      ? clause
          .replace(/[{}]/g, '')
          .split(',')
          // `export { default as x } from` 是在转发默认导出，不是在导入名为 default 的成员
          .map((s) => s.trim().split(/\s+as\s+/)[0].trim())
          .filter((n) => n && n !== 'default')
      : []
    out.push({
      spec: m[2],
      names: { default: clause.startsWith('*'), namespace: clause.startsWith('*'), named },
      kind: 'reexport',
    })
  }
  return out
}

/** 目标模块导出了哪些名字（含 re-export 链，向上递归若干层） */
async function exportedNamesOf(url, depth = 0) {
  const cached = exportCache.get(url)
  if (cached) return cached

  const res = await fetch(url)
  if (!res.ok) {
    const empty = { hasDefault: false, names: new Set(), isCjs: false, star: false }
    exportCache.set(url, empty)
    return empty
  }
  const code = await res.text()
  const names = new Set()
  let hasDefault = false
  let star = false

  if (/export\s+default\b/.test(code)) hasDefault = true
  if (/export\s*\{[^}]*\bdefault\b[^}]*\}/.test(code)) hasDefault = true

  let m
  const reNamed = /export\s+(?:async\s+)?(?:function|const|let|var|class)\s+([A-Za-z_$][\w$]*)/g
  while ((m = reNamed.exec(code))) names.add(m[1])
  const reBrace = /export\s*\{([^}]*)\}/g
  while ((m = reBrace.exec(code))) {
    for (const piece of m[1].split(',')) {
      const name = piece.trim().split(/\s+as\s+/).pop().trim()
      if (name && name !== 'default') names.add(name)
    }
  }
  if (/export\s+\*/.test(code)) star = true

  // 递归跟进 re-export，解析出真实导出的名字
  const reReexport = /export\s+([^'"]*?)\s*from\s*['"]([^'"]+)['"]/g
  while ((m = reReexport.exec(code))) {
    const clause = m[1].trim()
    if (clause.startsWith('*')) {
      star = true
    } else if (clause.startsWith('{')) {
      for (const piece of clause.replace(/[{}]/g, '').split(',')) {
        const name = piece.trim().split(/\s+as\s+/).pop().trim()
        if (name === 'default') hasDefault = true
        else if (name) names.add(name)
      }
    }
  }

  // 星号导出时，向下钻取以获得准确的名字集合
  if (star && depth < 3) {
    const reStar = /export\s+\*\s+from\s*['"]([^'"]+)['"]/g
    while ((m = reStar.exec(code))) {
      const child = await exportedNamesOf(resolveSpec(m[1], url), depth + 1)
      for (const n of child.names) names.add(n)
      if (child.hasDefault) hasDefault = true
    }
  }

  const result = {
    hasDefault,
    names,
    star,
    isCjs:
      !hasDefault &&
      names.size === 0 &&
      !star &&
      (/\bmodule\.exports\b|\bexports\.[A-Za-z_$]/.test(code) || /typeof exports\s*===/.test(code)),
  }
  exportCache.set(url, result)
  return result
}

const exportCache = new Map()

async function walk(url) {
  if (cache.has(url)) return cache.get(url)
  const promise = (async () => {
    const res = await fetch(url)
    if (!res.ok) return { ok: false, status: res.status, code: '' }
    const code = await res.text()
    return { ok: true, status: res.status, code, url }
  })()
  cache.set(url, promise)
  const info = await promise
  if (!info.ok) return info

  const deps = extractImports(info.code)
  for (const dep of deps) {
    // 跳过 Vite 客户端等虚拟模块
    if (dep.spec.startsWith('/@') || dep.spec.includes('?') || dep.spec.startsWith('virtual:')) continue
    const depUrl = resolveSpec(dep.spec, url)
    const child = await walk(depUrl)
    checked++

    if (!child.ok) {
      hardProblems.push(`[404] ${dep.spec}\n      被引用处: ${url}\n      HTTP ${child.status}`)
      continue
    }
    // 只对 node_modules 里的第三方依赖做 ESM 兼容性检查
    if (!/\/node_modules\//.test(depUrl)) continue

    const exp = await exportedNamesOf(depUrl)

    // 硬失败：目标是 CJS/UMD 却被当作 ESM 导入 —— 浏览器会直接报
    // "does not provide an export named 'default'" 并终止整个模块图
    if (exp.isCjs && (dep.names?.default || dep.names?.named?.length || dep.kind === 'side')) {
      hardProblems.push(
        `[CJS 依赖被当 ESM 导入] ${dep.spec}\n      被引用处: ${url}\n` +
          `      目标: ${depUrl}（无任何 ESM 导出，疑似 CJS/UMD 产物）`
      )
      continue
    }

    if (dep.names?.default && !exp.hasDefault && !exp.star) {
      warnings.push(`[可能缺少 default 导出] ${dep.spec}  <- ${url}`)
    }
    if (dep.names?.named?.length && !exp.star) {
      const missing = dep.names.named.filter((n) => !exp.names.has(n))
      if (missing.length) {
        warnings.push(`[可能缺少具名导出] ${dep.spec} -> ${missing.join(', ')}  <- ${url}`)
      }
    }
  }
  return info
}

const t0 = Date.now()
await walk(resolveSpec(ENTRY, BASE + '/'))
const secs = ((Date.now() - t0) / 1000).toFixed(1)

console.log(`\n=== 模块图校验（模块 ${cache.size} 个，依赖解析 ${checked} 次，用时 ${secs}s）===\n`)

if (hardProblems.length === 0) {
  console.log('  ✅ 无 404、无 CJS 依赖被当 ESM 导入')
} else {
  for (const p of [...new Set(hardProblems)].slice(0, 20)) console.log('  ❌ ' + p + '\n')
}

const uniqueWarn = [...new Set(warnings)]
if (uniqueWarn.length) {
  console.log(`  ⚠ ${uniqueWarn.length} 条导出分析提示（正则近似，多为误报，仅作参考）`)
  for (const w of uniqueWarn.slice(0, 5)) console.log('      ' + w)
  if (uniqueWarn.length > 5) console.log(`      ... 其余 ${uniqueWarn.length - 5} 条省略`)
}

console.log('\n' + '='.repeat(56))
console.log(hardProblems.length === 0 ? '✅ 通过（模块图可完整加载）' : `❌ 发现 ${new Set(hardProblems).size} 类硬性问题`)
console.log('='.repeat(56))
process.exit(hardProblems.length ? 1 : 0)
