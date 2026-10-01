import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { useMemo } from 'react'

// Whatever a document contains, it is only ever shown after this: scripts, handlers and the like are removed, links open in
// a new tab, and images that are not inside the document itself are dropped (a remote image would be fetched on opening).
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
  if (node.tagName === 'IMG' && !(node.getAttribute('src') ?? '').startsWith('data:')) {
    node.replaceWith(document.createTextNode(node.getAttribute('alt') ? `[${node.getAttribute('alt')}]` : '[afbeelding]'))
  }
})

const clean = (html: string) => DOMPurify.sanitize(html, { USE_PROFILES: { html: true } })

/** HTML (converted from a Word document) in the reading style, sanitized. */
export function RichHtml({ html }: { html: string }) {
  const safe = useMemo(() => clean(html), [html])
  return <div className="reader-prose px-4 py-3" dangerouslySetInnerHTML={{ __html: safe }} />
}

/** Markdown, formatted (GitHub flavour), sanitized. */
export function RichMarkdown({ text }: { text: string }) {
  const safe = useMemo(() => clean(marked.parse(text, { gfm: true, async: false }) as string), [text])
  return <div className="reader-prose px-4 py-3" dangerouslySetInnerHTML={{ __html: safe }} />
}
