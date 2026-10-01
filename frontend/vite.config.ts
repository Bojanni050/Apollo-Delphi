import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The build number is made when the frontend is built (or when the dev server starts), like melodiq's
// NEXT_PUBLIC_BUILD_VERSION: "0." + date and time, so every build and deploy gets a new one and nobody has to edit it.
const pad = (n: number) => String(n).padStart(2, '0')
const days = ['zo', 'ma', 'di', 'wo', 'do', 'vr', 'za']
const months = ['jan', 'feb', 'mrt', 'apr', 'mei', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec']
const now = new Date()
const BUILD_VERSION = `0.${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}`
const BUILD_TIME = `${days[now.getDay()]} ${now.getDate()} ${months[now.getMonth()]} ${now.getFullYear()} · ${pad(now.getHours())}:${pad(now.getMinutes())}`

export default defineConfig({
  plugins: [react()],
  define: {
    __BUILD_VERSION__: JSON.stringify(BUILD_VERSION),
    __BUILD_TIME__: JSON.stringify(BUILD_TIME),
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
