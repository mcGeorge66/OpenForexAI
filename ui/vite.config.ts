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
      // Proxy all API calls to the FastAPI backend during dev
      '/agents': httpTarget,
      '/health': httpTarget,
      '/version': httpTarget,
      '/metrics': httpTarget,
      '/routing': httpTarget,
      '/events': httpTarget,
      '/monitoring': httpTarget,
      '/indicators': httpTarget,
      '/tools': httpTarget,
      '/config': httpTarget,
      '/runtime': httpTarget,
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
