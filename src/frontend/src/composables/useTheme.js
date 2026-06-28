import {useDark, useToggle} from '@vueuse/core'

export const isDark = useDark({
  storageKey: 'mcpacklocalizer-theme-appearance'
})

export const toggleDark = useToggle(isDark)