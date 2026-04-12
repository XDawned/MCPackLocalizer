/**
 * 整合包提取界面组件
 */
<template>
  <div class="extract-interface">
    <h2>整合包待翻译部分提取</h2>
    <p>整合包提取界面 - 从整合包中提取待翻译的模组、任务文件</p>
    <p class="placeholder-text">此组件需要实现以下功能：</p>
    <ul>
      <li>选择整合包目录</li>
      <li>扫描模组文件</li>
      <li>扫描 FTBQuests 任务文件</li>
      <li>扫描 BetterQuesting 任务文件</li>
      <li>提取语言文件到工作目录</li>
    </ul>
  </div>
</template>

<script setup>
// 整合包提取逻辑
</script>

<style scoped>
.extract-interface {
  padding: 20px;
  height: 100%;
  overflow: auto;
}

.extract-interface h2 {
  margin-bottom: 16px;
  color: var(--text-color);
}

.placeholder-text {
  color: var(--text-secondary-color);
  margin: 16px 0;
}

.extract-interface ul {
  color: var(--text-secondary-color);
  margin-left: 20px;
}

.extract-interface li {
  margin: 8px 0;
}
</style>