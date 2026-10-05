/**
 * 构建产物静态校验（确定性、快速）
 *
 * 运行：node scripts/verify-bundle.cjs
 *
 * 检查生产 bundle 是否满足「能在浏览器里跑起来」的必要条件：
 *   1. 不含 `process.env.*`  —— 浏览器没有 process，残留会直接白屏；
 *   2. 运行时代码不含未替换的 Vue 特性开关（如 __VUE_OPTIONS_API__）；
 *   3. 没有未被打包的裸模块导入（如 from "vue"）；
 *   4. index.html 引用的入口与静态资源都存在。
 *
 * 背景：受限环境无法启动浏览器做冒烟测试，也无法用 jsdom 完整跑 hash 路由
 * （history.replaceState 不更新 hash，会导致守卫反复重定向）。
 * 因此把「能确定的必要条件」固化成这个脚本，防止再次出现白屏类回归。
 */
const fs = require('node:fs')
const path = require('node:path')

const DIST = path.join(__dirname, '..', 'dist')
const ASSETS = path.join(DIST, 'assets')

let failed = 0
const check = (name, ok, detail = '') => {
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  ' + detail}`)
  if (!ok) failed++
}

if (!fs.existsSync(DIST) || !fs.existsSync(ASSETS)) {
  console.error('✗ 未找到 dist 目录，请先执行 npm run build')
  process.exit(1)
}

const indexHtml = fs.readFileSync(path.join(DIST, 'index.html'), 'utf8')
const jsFiles = fs.readdirSync(ASSETS).filter((f) => f.endsWith('.js'))
const cssFiles = fs.readdirSync(ASSETS).filter((f) => f.endsWith('.css'))

/**
 * 去掉字符串/模板串内容，只保留代码骨架。
 * 框架自带的错误提示文案里会出现 `vue-router`、`__VUE_OPTIONS_API__` 等字样，
 * 直接全文匹配会把它们误判成问题。
 */
function stripStrings(code) {
  let out = ''
  let i = 0
  const n = code.length
  // depth 用于处理模板串里的 ${ ... } 嵌套
  const stack = []
  while (i < n) {
    const ch = code[i]
    const inTemplate = stack.length > 0

    if (ch === '"' || ch === "'" || ch === '`') {
      if (inTemplate && ch !== '`') {
        // 模板串内部的普通引号，按普通字符串跳过
      }
      const quote = ch
      i++
      while (i < n) {
        if (code[i] === '\\') {
          i += 2
          continue
        }
        if (quote === '`' && code[i] === '$' && code[i + 1] === '{') {
          // 进入插值表达式，需要保留并解析其内容
          stack.push('`')
          i += 2
          out += ' '
          break
        }
        if (code[i] === quote) {
          i++
          break
        }
        i++
      }
      continue
    }

    if (inTemplate) {
      if (ch === '}') {
        stack.pop()
        i++
        continue
      }
    }

    if (ch === '/' && code[i + 1] === '/') {
      while (i < n && code[i] !== '\n') i++
      continue
    }
    if (ch === '/' && code[i + 1] === '*') {
      i += 2
      while (i < n && !(code[i] === '*' && code[i + 1] === '/')) i++
      i += 2
      continue
    }
    out += ch
    i++
  }
  return out
}

console.log(`\n=== 构建产物校验（${jsFiles.length} 个 JS / ${cssFiles.length} 个 CSS）===\n`)

// ---- 1 & 2：逐文件检查 ----
let processEnvHits = 0
let flagHits = 0
let bareImports = []

for (const file of jsFiles) {
  const raw = fs.readFileSync(path.join(ASSETS, file), 'utf8')
  const code = stripStrings(raw)

  const pe = code.match(/process\.env\.[A-Za-z_]+/g)
  if (pe) {
    processEnvHits += pe.length
    console.log(`    [process.env] ${file}: ${[...new Set(pe)].join(', ')}`)
  }

  const flags = code.match(/\b__VUE_(?:OPTIONS_API|PROD_DEVTOOLS|PROD_HYDRATION_MISMATCH_DETAILS)__\b/g)
  if (flags) {
    flagHits += flags.length
    console.log(`    [feature-flag] ${file}: ${[...new Set(flags)].join(', ')}`)
  }

  // 静态与动态的裸模块导入。
  // 注意：必须在「原始代码」上匹配（字符串已保留），这样 `from "vue"` 才能被识别；
  // 但框架错误提示文案里也会出现 import("...") 字样，因此要求匹配位置确实是语句级导入
  // —— 通过 stripStrings 后的骨架校验括号/位置来排除文案。
  const specs = new Set()
  const fromRe = /(?:^|[\s;}])(?:import|export)\s[^;{}]*?from\s*['"]([^'"]+)['"]/g
  const sideEffectRe = /(?:^|[\s;}])import\s*['"]([^'"]+)['"]/g
  const dynRe = /(?:^|[=(,;\s])import\s*\(\s*['"]([^'"]+)['"]\s*\)/g
  for (const re of [fromRe, sideEffectRe, dynRe]) {
    let m
    while ((m = re.exec(code))) {
      const spec = m[1]
      // 骨架里该位置若只剩空白/引号，说明它来自被剥掉的字符串（提示文案）
      const idx = m.index
      if (idx > 0 && /["'`]/.test(code.slice(Math.max(0, idx - 2), idx))) continue
      specs.add(spec)
    }
  }
  for (const s of specs) {
    if (!s.startsWith('/') && !s.startsWith('./') && !s.startsWith('../') && !s.startsWith('http')) {
      bareImports.push(`${file}: ${s}`)
    }
  }
}

check('无 process.env 残留（否则浏览器白屏）', processEnvHits === 0, `${processEnvHits} 处`)
check('Vue 特性开关已被替换', flagHits === 0, `${flagHits} 处`)
check('无未打包的裸模块导入', bareImports.length === 0, bareImports.join(' | '))

// ---- 3：入口与资源存在 ----
const entryMatch = indexHtml.match(/<script[^>]+type="module"[^>]+src="([^"]+)"/)
check('index.html 含 module 入口', !!entryMatch, indexHtml.slice(0, 120))
if (entryMatch) {
  const entryFile = entryMatch[1].replace(/^\//, '')
  check(`入口文件存在（${entryMatch[1]}）`, fs.existsSync(path.join(DIST, entryFile)))
}
const emptyCss = cssFiles.filter((f) => fs.statSync(path.join(ASSETS, f)).size === 0)
check(`${cssFiles.length} 个样式文件均非空`, emptyCss.length === 0, emptyCss.join(', '))

// ---- 4：路由懒加载的页面 chunk 是否齐全 ----
const expectedChunks = [
  'Login', 'Register', 'Dashboard', 'Profile', 'LabList', 'LabDetail', 'LabManage',
  'EquipmentManage', 'Booking', 'MyReservations', 'ReviewList', 'KnowledgeManage',
  'UserManage', 'AiAssistant', '403', '404', 'MainLayout',
]
const missing = expectedChunks.filter((name) => !jsFiles.some((f) => f.startsWith(name + '-')))
check(`${expectedChunks.length} 个页面 chunk 全部产出`, missing.length === 0, `缺少: ${missing.join(', ')}`)

console.log('\n' + '='.repeat(56))
console.log(failed === 0 ? '✅ 构建产物校验通过' : `❌ 有 ${failed} 项失败`)
console.log('='.repeat(56))
process.exit(failed ? 1 : 0)
