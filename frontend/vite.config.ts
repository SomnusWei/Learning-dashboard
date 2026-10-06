import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'node:path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // 默认使用同源（相对路径），兼容域名和 IP 访问；
  // 如需跨域部署，可通过 .env 设置 VITE_API_BASE 为完整 URL。
  const apiBase = env.VITE_API_BASE || ''

  return {
    plugins: [
      vue(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['favicon.svg', 'robots.txt'],
        manifest: {
          name: '个人学习工作台',
          short_name: '学习台',
          description: '中医学个人学习工作台 - 错题/计划/待办/记忆',
          theme_color: '#5B8DEF',
          background_color: '#1A1A2E',
          display: 'standalone',
          orientation: 'portrait',
          scope: '/',
          start_url: '/',
          lang: 'zh-CN',
          icons: [
            {
              src: '/pwa-192.png',
              sizes: '192x192',
              type: 'image/png',
              purpose: 'any maskable'
            },
            {
              src: '/pwa-512.png',
              sizes: '512x512',
              type: 'image/png',
              purpose: 'any maskable'
            }
          ]
        },
        workbox: {
          // 仅缓存静态资源（JS/CSS/HTML），不缓存业务数据
          globPatterns: ['**/*.{js,css,html,svg,png,ico,woff,woff2}'],
          maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
          runtimeCaching: []
        },
        devOptions: {
          enabled: false
        }
      })
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src')
      }
    },
    server: {
      port: 5173,
      host: '0.0.0.0',
      proxy: {
        '/api': {
          target: env.VITE_DEV_API || 'http://localhost:8000',
          changeOrigin: true
        }
      }
    },
    define: {
      __API_BASE__: JSON.stringify(apiBase)
    }
  }
})
