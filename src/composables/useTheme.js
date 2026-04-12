/**
 * 主题切换组合式函数
 */
import { ref, computed } from 'vue'

// 从 localStorage 读取主题
const storedTheme = localStorage.getItem('theme') || 'dark'

export function useTheme() {
  const theme = ref(storedTheme)

  const toggleTheme = () => {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    localStorage.setItem('theme', theme.value)
    document.body.setAttribute('data-theme', theme.value)
  }

  const isDark = computed(() => theme.value === 'dark')
  const isLight = computed(() => theme.value === 'light')

  return {
    theme,
    toggleTheme,
    isDark,
    isLight,
  }
}