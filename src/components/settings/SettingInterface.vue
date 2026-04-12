/**
 * 设置界面组件
 */
<template>
  <div class="setting-interface">
    <h2>通用配置</h2>
    <p>设置界面 - 配置工作目录、翻译 API、个性化等</p>
    <p class="placeholder-text">此组件需要实现以下功能：</p>
    <ul>
      <li>工作目录配置</li>
      <li>缓存目录配置</li>
      <li>翻译 API 选择（百度翻译、离线翻译、OpenAI）</li>
      <li>API 密钥配置</li>
      <li>主题设置（明亮/黑暗/跟随系统）</li>
      <li>界面缩放</li>
      <li>关于信息</li>
    </ul>
  </div>
</template>

<script setup>
// 设置逻辑
</script>

<style scoped>
.setting-interface {
  padding: 20px;
  height: 100%;
  overflow: auto;
}

.setting-interface h2 {
  margin-bottom: 16px;
  color: var(--text-color);
}

.placeholder-text {
  color: var(--text-secondary-color);
  margin: 16px 0;
}

.setting-interface ul {
  color: var(--text-secondary-color);
  margin-left: 20px;
}

.setting-interface li {
  margin: 8px 0;
}
</style>