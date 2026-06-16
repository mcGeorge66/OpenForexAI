/**
 * Shared utility: create a document in the [Import] folder of the Knowledgebase.
 * The folder is created automatically on first use.
 */
import { api } from '@/api/client'

function ts(): string {
  const d = new Date()
  const pad = (n: number, l = 2) => String(n).padStart(l, '0')
  return (
    d.getFullYear() +
    pad(d.getMonth() + 1) +
    pad(d.getDate()) +
    pad(d.getHours()) +
    pad(d.getMinutes())
  )
}

async function getOrCreateImportFolder(): Promise<string> {
  const docs = await api.kbListDocuments()
  const existing = docs.find(d => d.title === '[Import]' && d.is_folder)
  if (existing) return existing.id
  const result = await api.kbCreateDocument({ title: '[Import]', is_folder: 1 })
  return result.id
}

export async function kbImport(type: string, content: string): Promise<void> {
  const folderId = await getOrCreateImportFolder()
  const title = `${type}_${ts()}`
  await api.kbCreateDocument({
    title,
    content,
    is_folder: 0,
    parent_id: folderId,
  })
}
