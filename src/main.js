/**
 * Vue 3 应用入口
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './index.css'

// 注册 Fluent UI Web Components
import { 
  provideFluentDesignSystem,
  fluentButton,
  fluentCard,
  fluentTextField,
  fluentDropdown,
  fluentOption,
  fluentProgressRing,
  fluentDialog,
  fluentSwitch,
  fluentTabs,
  fluentTab,
  fluentTabPanel,
  fluentTabList,
  fluentDataGrid,
  fluentDataGridRow,
  fluentDataGridCell,
  fluentToolbar,
  fluentBreadcrumb,
  fluentBreadcrumbItem,
} from '@fluentui/web-components'

// 注册 Fluent UI 组件
provideFluentDesignSystem().register(
  fluentButton(),
  fluentCard(),
  fluentTextField(),
  fluentDropdown(),
  fluentOption(),
  fluentProgressRing(),
  fluentDialog(),
  fluentSwitch(),
  fluentTabs(),
  fluentTab(),
  fluentTabPanel(),
  fluentTabList(),
  fluentDataGrid(),
  fluentDataGridRow(),
  fluentDataGridCell(),
  fluentToolbar(),
  fluentBreadcrumb(),
  fluentBreadcrumbItem(),
)

// 创建应用
const app = createApp(App)
const pinia = createPinia()

// 使用插件
app.use(pinia)
app.use(router)

// 挂载应用
app.mount('#app')