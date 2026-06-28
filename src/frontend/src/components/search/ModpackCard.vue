<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElAvatar, ElTag, ElDivider } from 'element-plus'

const props = defineProps({
  item: { type: Object, required: true }
})

const router = useRouter()

function formatDownloads(num) {
  if (num == null) return '未知'
  if (num >= 100000000) return (num / 100000000).toFixed(1) + '亿'
  if (num >= 10000) return (num / 10000).toFixed(1) + '万'
  return num.toLocaleString()
}

function formatDate(isoStr) {
  if (!isoStr) return ''
  try {
    const d = new Date(isoStr)
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
  } catch {
    return isoStr
  }
}

const platformLabel = computed(() =>
  props.item.platform === 'curseforge' ? 'CurseForge' : 'Modrinth'
)

function goDetail() {
  router.push({
    name: 'modpackDetail',
    params: {
      platform: props.item.platform,
      id: props.item.id
    }
  })
}
</script>

<template>
  <div class="modpack-card" @click="goDetail">
    <div class="card-inner">
      <div class="card-icon">
        <el-avatar
          :src="item.icon_url"
          shape="square"
          :size="72"
          class="icon-avatar"
        >
          📦
        </el-avatar>
      </div>

      <div class="card-body">
        <div class="card-header">
          <div class="card-title-block">
            <span class="card-title">{{ item.name }}</span>
            <div class="card-meta">
              <span v-if="item.author" class="card-author">{{ item.author }}</span>
              <el-divider v-if="item.author" direction="vertical" class="meta-divider" />
              <span class="card-downloads">
                下载量 {{ formatDownloads(item.download_count) }}
              </span>
              <el-divider direction="vertical" class="meta-divider" />
              <span class="card-updated">更新于 {{ formatDate(item.last_updated) || '未知' }}</span>
            </div>
          </div>

          <div class="card-badges">
            <el-tag
              size="small"
              class="tag-platform"
              :class="item.platform === 'curseforge' ? 'tag-platform--cf' : 'tag-platform--mr'"
            >
              {{ platformLabel }}
            </el-tag>
            <el-tag
              v-for="loader in item.loaders"
              :key="loader"
              size="small"
              class="tag-loader"
            >
              {{ loader }}
            </el-tag>
          </div>
        </div>

        <p v-if="item.summary" class="card-summary">{{ item.summary }}</p>

        <div class="card-tags" v-if="item.game_versions?.length || item.categories?.length">
          <el-tag
            v-for="v in item.game_versions"
            :key="'v-' + v"
            size="small"
            class="tag-version"
          >
            {{ v }}
          </el-tag>
          <el-tag
            v-for="c in item.categories"
            :key="'c-' + c"
            size="small"
            class="tag-category"
          >
            {{ c }}
          </el-tag>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.modpack-card {
  background: linear-gradient(180deg, var(--fluent-surface-3), var(--fluent-surface-2));
  border-radius: var(--notion-rounded-lg);
  border: 1px solid var(--notion-hairline-soft);
  padding: var(--notion-spacing-lg);
  cursor: pointer;
  box-shadow: var(--notion-shadow-subtle);
  transition:
    border-color var(--notion-transition-normal),
    box-shadow var(--notion-transition-normal),
    transform var(--notion-transition-fast),
    background-color var(--notion-transition-fast);

  &:hover {
    border-color: var(--fluent-border-accent);
    box-shadow: var(--notion-shadow-card);
    transform: translateY(-1px);
  }

  &:active {
    transform: translateY(0);
  }
}

.card-inner {
  display: flex;
  gap: var(--notion-spacing-md);
  align-items: flex-start;
}

.card-icon {
  flex-shrink: 0;
  padding-top: 2px;
}

.icon-avatar {
  border-radius: var(--notion-rounded-md);
  border: 1px solid var(--notion-hairline-soft);
}

.card-body {
  flex: 1;
  min-width: 0;
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;

  @media (max-width: 768px) {
    flex-direction: column;
  }
}

.card-title-block {
  min-width: 0;
}

.card-title {
  display: block;
  font-size: var(--notion-font-size-body);
  font-weight: 600;
  color: var(--notion-ink);
  line-height: 1.4;
  word-break: break-word;
  margin-bottom: 4px;
}

.card-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  color: var(--notion-steel);
  font-size: var(--notion-font-size-caption);
}

.card-author {
  color: var(--notion-slate);
}

.card-downloads,
.card-updated {
  color: var(--notion-steel);
}

.card-badges {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 6px;
  flex-shrink: 0;
}

.card-summary {
  margin: 0 0 10px 0;
  color: var(--notion-slate);
  font-size: var(--notion-font-size-caption);
  line-height: var(--notion-line-height-body-sm);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

:deep(.tag-platform),
:deep(.tag-loader),
:deep(.tag-version),
:deep(.tag-category) {
  border-radius: var(--notion-rounded-sm);
  font-weight: 500;
}

:deep(.tag-platform--cf) {
  background-color: rgba(107, 79, 211, 0.12);
  border-color: rgba(107, 79, 211, 0.24);
  color: var(--notion-brand-purple-800);
}

:deep(.tag-platform--mr) {
  background-color: rgba(15, 118, 110, 0.12);
  border-color: rgba(15, 118, 110, 0.24);
  color: var(--notion-brand-teal);
}

:deep(.tag-loader) {
  background-color: var(--fluent-surface-inset);
  border-color: var(--notion-hairline-soft);
  color: var(--notion-slate);
}

:deep(.tag-version) {
  background-color: rgba(16, 124, 16, 0.1);
  border-color: rgba(16, 124, 16, 0.2);
  color: var(--notion-semantic-success);
}

:deep(.tag-category) {
  background-color: var(--fluent-surface-accent-subtle);
  border-color: var(--notion-hairline-soft);
  color: var(--notion-slate);
}

:deep(.meta-divider) {
  border-color: var(--notion-hairline);
}

@media (max-width: 576px) {
  .card-inner {
    gap: var(--notion-spacing-sm);
  }

  .card-icon :deep(.el-avatar) {
    width: 56px !important;
    height: 56px !important;
  }
}
</style>
