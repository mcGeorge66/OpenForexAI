import { useEffect, useState } from 'react'
import { Edit3, RefreshCw, Save, X } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '@/api/client'

export function InformationView() {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  const load = () => {
    setLoading(true)
    setError(null)
    setStatus(null)
    api.getProjectReadmeText()
      .then(raw => {
        setText(raw)
        setDraft(raw)
        setLoading(false)
      })
      .catch(err => {
        setError(String(err))
        setLoading(false)
      })
  }

  useEffect(() => {
    load()
  }, [])

  const startEdit = () => {
    setDraft(text)
    setEditing(true)
    setStatus(null)
    setError(null)
  }

  const cancelEdit = () => {
    setDraft(text)
    setEditing(false)
    setStatus(null)
  }

  const save = async () => {
    setSaving(true)
    setError(null)
    setStatus(null)
    try {
      await api.saveProjectReadmeText(draft)
      setText(draft)
      setEditing(false)
      setStatus('Saved.')
    } catch (err) {
      setError(String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <span className="text-sm text-gray-300 font-medium">Information</span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">D:\\GitHub\\GHG\\OpenForexAI\\config\\config.md</span>
          {!editing && (
            <button
              onClick={startEdit}
              disabled={loading}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors"
            >
              <Edit3 className="w-3.5 h-3.5" />
              Edit
            </button>
          )}
          <button
            onClick={load}
            disabled={loading || saving}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          {editing && (
            <>
              <button
                onClick={() => void save()}
                disabled={saving}
                className="flex items-center gap-1 text-xs text-emerald-300 hover:text-emerald-200 transition-colors disabled:opacity-50"
              >
                <Save className={`w-3.5 h-3.5 ${saving ? 'animate-pulse' : ''}`} />
                Save
              </button>
              <button
                onClick={cancelEdit}
                disabled={saving}
                className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-50"
              >
                <X className="w-3.5 h-3.5" />
                Cancel
              </button>
            </>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4 bg-gray-950">
        {loading && <p className="text-gray-500 text-sm animate-pulse">Loading…</p>}
        {status && <p className="text-emerald-400 text-sm mb-2">{status}</p>}
        {error && <p className="text-red-400 text-sm mb-2">Error: {error}</p>}
        {!loading && !error && editing && (
          <div className="h-full min-h-[420px]">
            <textarea
              value={draft}
              onChange={e => setDraft(e.target.value)}
              className="w-full h-full min-h-[420px] resize-y bg-gray-900 text-gray-200 text-sm rounded border border-gray-700 px-3 py-2 font-mono leading-6 focus:outline-none focus:border-emerald-500"
            />
          </div>
        )}
        {!loading && !error && !editing && (
          <article
            className={[
              'max-w-none text-sm text-gray-200 leading-7',
              '[&_h1]:text-3xl [&_h1]:font-semibold [&_h1]:text-white [&_h1]:mt-6 [&_h1]:mb-4 [&_h1]:border-b [&_h1]:border-gray-700 [&_h1]:pb-2',
              '[&_h2]:text-2xl [&_h2]:font-semibold [&_h2]:text-white [&_h2]:mt-6 [&_h2]:mb-3',
              '[&_h3]:text-xl [&_h3]:font-semibold [&_h3]:text-gray-100 [&_h3]:mt-5 [&_h3]:mb-2',
              '[&_h4]:text-lg [&_h4]:font-semibold [&_h4]:text-gray-100 [&_h4]:mt-4 [&_h4]:mb-2',
              '[&_p]:my-3 [&_p]:text-gray-300',
              '[&_ul]:list-disc [&_ul]:pl-6 [&_ul]:my-3',
              '[&_ol]:list-decimal [&_ol]:pl-6 [&_ol]:my-3',
              '[&_li]:my-1 [&_li]:text-gray-300',
              '[&_a]:text-cyan-300 hover:[&_a]:text-cyan-200 [&_a]:underline [&_a]:underline-offset-2',
              '[&_blockquote]:border-l-4 [&_blockquote]:border-gray-600 [&_blockquote]:pl-4 [&_blockquote]:italic [&_blockquote]:text-gray-400 [&_blockquote]:my-4',
              '[&_code]:font-mono [&_code]:text-emerald-300 [&_code]:bg-gray-900 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded',
              '[&_pre]:bg-gray-900 [&_pre]:border [&_pre]:border-gray-700 [&_pre]:rounded [&_pre]:p-3 [&_pre]:overflow-auto [&_pre]:my-4',
              '[&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:rounded-none',
              '[&_table]:w-full [&_table]:border-collapse [&_table]:my-4 [&_table]:text-sm',
              '[&_thead_th]:text-left [&_thead_th]:text-gray-200 [&_thead_th]:font-semibold [&_thead_th]:border-b [&_thead_th]:border-gray-600 [&_thead_th]:px-3 [&_thead_th]:py-2',
              '[&_tbody_td]:border-b [&_tbody_td]:border-gray-800 [&_tbody_td]:px-3 [&_tbody_td]:py-2 [&_tbody_td]:text-gray-300',
              '[&_hr]:border-gray-700 [&_hr]:my-6',
            ].join(' ')}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
          </article>
        )}
      </div>
    </div>
  )
}
