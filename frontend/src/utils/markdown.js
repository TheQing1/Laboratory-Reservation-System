import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

/** 把 Markdown 文本渲染为 HTML（用于 AI 回答展示）。 */
export function renderMarkdown(text) {
  if (!text) return ''
  return md.render(String(text))
}

export default md
