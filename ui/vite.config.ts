import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'
import JSON5 from 'json5'

type GenericObject = Record<string, unknown>

function isObject(value: unknown): value is GenericObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function deepMerge(base: unknown, override: unknown): unknown {
  if (Array.isArray(base) && Array.isArray(override)) return override
  if (isObject(base) && isObject(override)) {
    const out: GenericObject = { ...base }
    for (const [key, value] of Object.entries(override)) {
      out[key] = key in out ? deepMerge(out[key], value) : value
    }
    return out
  }
  return override
}

function loadRuntimeConfig(): GenericObject {
  const repoRoot = path.resolve(__dirname, '..')
  const configDir = path.join(repoRoot, 'config')
  const defaultPath = path.join(configDir, 'config.default.json5')
  const systemPath = path.join(configDir, 'system.json5')
  const defaultCfg = fs.existsSync(defaultPath)
    ? JSON5.parse(fs.readFileSync(defaultPath, 'utf8')) as GenericObject
    : {}
  const systemCfg = fs.existsSync(systemPath)
    ? JSON5.parse(fs.readFileSync(systemPath, 'utf8')) as GenericObject
    : {}
  return deepMerge(defaultCfg, systemCfg) as GenericObject
}

const runtimeConfig = loadRuntimeConfig()
const systemConfig = isObject(runtimeConfig.system) ? runtimeConfig.system : {}
const managementApi = isObject(systemConfig.management_api) ? systemConfig.management_api : {}
const uiConfig = isObject(systemConfig.ui) ? systemConfig.ui : {}
const devServer = isObject(uiConfig.dev_server) ? uiConfig.dev_server : {}

const managementHost = typeof managementApi.host === 'string' && managementApi.host.trim()
  ? managementApi.host.trim()
  : '127.0.0.1'
const managementPort = typeof managementApi.port === 'number'
  ? managementApi.port
  : Number(managementApi.port ?? 8765)
const devHost = typeof devServer.host === 'string' && devServer.host.trim()
  ? devServer.host.trim()
  : '127.0.0.1'
const devPort = typeof devServer.port === 'number'
  ? devServer.port
  : Number(devServer.port ?? 5173)
const httpTarget = `http://${managementHost}:${managementPort}`
const wsTarget = `ws://${managementHost}:${managementPort}`

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: devHost,
    port: devPort,
    proxy: {
      // Proxy all API calls to the FastAPI backend during dev. Kept in sync with
      // every top-level route prefix registered on either backend router —
      // openforexai/management/api.py's `router` and handbook_router.py's `/kb`
      // router — not just the ones some feature happened to need when this list
      // was last touched. A path missing here doesn't error, it silently falls
      // through to Vite's SPA index.html, which then fails JSON parsing with a
      // confusing "Unexpected token '<'" — much harder to diagnose than a
      // missing-entry gap should be.
      '/agents': httpTarget,
      '/analyses': httpTarget,
      '/candles': httpTarget,
      '/chartshots': httpTarget,
      '/composers': httpTarget,
      '/config': httpTarget,
      '/console': httpTarget,
      '/debug': httpTarget,
      '/docs': httpTarget,
      '/entity-history': httpTarget,
      '/events': httpTarget,
      '/health': httpTarget,
      '/image': httpTarget,
      '/indicators': httpTarget,
      '/kb': httpTarget,
      '/llm-assistant': httpTarget,
      '/llm-contexts': httpTarget,
      '/metrics': httpTarget,
      '/monitoring': httpTarget,
      '/orderbook': httpTarget,
      '/prompt-workbench': httpTarget,
      '/routing': httpTarget,
      '/runtime': httpTarget,
      '/scripts': httpTarget,
      '/system': httpTarget,
      '/test': httpTarget,
      '/tools': httpTarget,
      '/version': httpTarget,
      '/ws': {
        target: wsTarget,
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
