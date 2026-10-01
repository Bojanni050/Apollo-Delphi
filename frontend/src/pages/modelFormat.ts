import type { ModelInfo } from '../api'

/** USD per 1M tokens: "$2.00", "$0.06"; 0 is "Free"; unknown is a dash. */
export function price(perMillion: number | null | undefined): string {
  if (perMillion == null) return '—'
  if (perMillion === 0) return 'Free'
  if (perMillion >= 100) return `$${perMillion.toFixed(0)}`
  if (perMillion >= 0.1) return `$${perMillion.toFixed(2)}`
  return `$${Number(perMillion.toPrecision(2))}` // 0.06, 0.015: keep the significant digits of small prices
}

/** 8192 -> "8.2K", 1050000 -> "1.05M". */
export function context(tokens: number): string {
  if (tokens >= 1_000_000) return `${Number((tokens / 1_000_000).toFixed(2))}M`
  if (tokens >= 1_000) return `${Number((tokens / 1_000).toFixed(1))}K`
  return String(tokens)
}

/** Descriptions are often markdown; show links as their text. */
export const plain = (text: string) => text.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/[*_`]+/g, '')

export const MODALITIES: Record<string, string> = {
  text: 'Tekst',
  image: 'Afbeeldingen (vision)',
  file: 'Bestanden / PDF',
  audio: 'Audio',
  video: 'Video',
  embedding: 'Embeddings',
}

export const FEATURES: Record<string, string> = {
  tools: 'Tools (function calling)',
  parallel_tools: 'Parallelle tool-aanroepen',
  reasoning: 'Redeneren',
  structured_output: 'Gestructureerde uitvoer (JSON)',
  web_search: 'Web search',
  prompt_caching: 'Prompt caching',
  computer_use: 'Computergebruik',
}

/** Whether there is more to tell about a model than its id (so "Lees meer" has something to open). */
export function hasDetails(m: ModelInfo): boolean {
  return Boolean(
    m.description || m.name || m.context_length || m.max_output_tokens || m.created || m.regions?.length ||
      m.input_modalities?.length || m.output_modalities?.length || m.features?.length ||
      m.input_per_million != null || m.output_per_million != null,
  )
}
