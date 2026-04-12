/**
 * 生成资源包界面组件
 */
<template>
  <div class="resourcepack-interface">
    <h2>生成汉化资源包</h2>
    <p>资源包生成界面 - 将翻译完成的语言文件打包为游戏资源包</p>
    <p class="placeholder-text">此组件需要实现以下功能：</p>
    <ul>
      <li>选择工作目录</li>
      <li>配置资源包元数据（名称、描述、版本）</li>
      <li>生成 pack.mcmeta 文件</li>
      <li>打包为 zip 格式</li>
    </ul>
  </div>
</template>

<script setup>
// 资源包生成逻辑
</script>

<style scoped>
.resourcepack-interface {
  padding: 20px;
  height: 100%;
  overflow: auto;
}

.resourcepack-interface h2 {
  margin-bottom: 16px;
  color: var(--text-color);
}

.placeholder-text {
  color: var(--text-secondary-color);
  margin: 16px 0;
}

.resourcepack-interface ul {
  color: var(--text-secondary-color);
  margin-left: 20px;
}

.resourcepack-interface li {
  margin: 8px 0;
}
</style>