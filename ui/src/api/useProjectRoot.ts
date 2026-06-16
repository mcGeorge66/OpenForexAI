import { useEffect, useState } from 'react'
import { api } from './client'

let _cached: string | null = null
let _promise: Promise<string> | null = null

function fetchRoot(): Promise<string> {
  if (_cached !== null) return Promise.resolve(_cached)
  if (_promise) return _promise
  _promise = api.getProjectRoot().then(({ root }) => {
    _cached = root
    return root
  })
  return _promise
}

export function joinPath(root: string, ...parts: string[]): string {
  const sep = root.includes('\\') ? '\\' : '/'
  return [root, ...parts].join(sep)
}

export function useProjectRoot(): string {
  const [root, setRoot] = useState(_cached ?? '')
  useEffect(() => {
    if (_cached) { setRoot(_cached); return }
    fetchRoot().then(setRoot).catch(() => {})
  }, [])
  return root
}
