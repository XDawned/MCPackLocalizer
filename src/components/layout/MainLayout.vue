/**
 * 主布局组件
 */
<template>
  <div class="main-layout">
    <fluent-tabs v-model="activeTab" orientation="vertical" class="main-tabs">
      <fluent-tab-list slot="tab" class="navigation">
        <fluent-tab id="work">
          <div class="tab-content">
            <span class="tab-icon">✎</span>
            <span>工作台</span>
          </div>
        </fluent-tab>
        <fluent-tab id="extract">
          <div class="tab-content">
            <span class="tab-icon">📁</span>
            <span>整合包提取</span>
          </div>
        </fluent-tab>
        <fluent-tab id="resourcepack">
          <div class="tab-content">
            <span class="tab-icon">📦</span>
            <span>生成资源包</span>
          </div>
        </fluent-tab>
        <fluent-tab id="settings">
          <div class="tab-content">
            <span class="tab-icon">⚙</span>
            <span>设置</span>
          </div>
        </fluent-tab>
      </fluent-tab-list>
      
      <fluent-tab-panel id="work" class="tab-panel">
        <WorkInterface />
      </fluent-tab-panel>
      
      <fluent-tab-panel id="extract" class="tab-panel">
        <ModpackExtractInterface />
      </fluent-tab-panel>
      
      <fluent-tab-panel id="resourcepack" class="tab-panel">
        <GenerateResourcepackInterface />
      </fluent-tab-panel>
      
      <fluent-tab-panel id="settings" class="tab-panel">
        <SettingInterface />
      </fluent-tab-panel>
    </fluent-tabs>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import WorkInterface from '../work/WorkInterface.vue'
import ModpackExtractInterface from '../extract/ModpackExtractInterface.vue'
import GenerateResourcepackInterface from '../resourcepack/GenerateResourcepackInterface.vue'
import SettingInterface from '../settings/SettingInterface.vue'

const activeTab = ref('work')
</script>

<style scoped>
.main-layout {
  height: calc(100vh - var(--title-bar-height));
  overflow: hidden;
}

.main-tabs {
  height: 100%;
  display: flex;
}

.navigation {
  width: var(--navigation-width);
  background-color: var(--surface-color);
  border-right: 1px solid var(--border-color);
  padding: 8px 0;
}

.tab-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tab-icon {
  font-size: 16px;
}

.tab-panel {
  flex: 1;
  overflow: auto;
  padding: 0;
}

fluent-tab-panel {
  flex: 1;
  overflow: hidden;
}
</style>