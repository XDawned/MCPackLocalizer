<script setup>
import { onMounted, onBeforeUnmount, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElButton, ElAvatar, ElTag, ElDivider, ElEmpty, ElSkeleton } from 'element-plus'
import { useModpackStore } from '@/stores/modpack'
import VersionSelector from '@/components/detail/VersionSelector.vue'
import ModListPreview from '@/components/detail/ModListPreview.vue'

const route = useRoute()
const router = useRouter()
const modpackStore = useModpackStore()

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

const platformTagType = computed(() =>
  modpackStore.detail?.platform === 'curseforge' ? 'warning' : 'success'
)

const platformLabel = computed(() =>
  modpackStore.detail?.platform === 'curseforge' ? 'CurseForge' : 'Modrinth'
)

const externalUrl = computed(() => {
  const d = modpackStore.detail
  if (!d?.slug || !d?.platform) return null
  return d.platform === 'curseforge'
    ? `https://www.curseforge.com/minecraft/modpacks/${d.slug}`
    : `https://modrinth.com/modpack/${d.slug}`
})

onMounted(() => {
  const platform = route.params.platform
  const id = route.params.id
  if (platform && id) {
    modpackStore.init(platform, id)
  }
})

onBeforeUnmount(() => {
  modpackStore.reset()
})

function goBack() {
  router.back()
}

function retry() {
  const platform = route.params.platform
  const id = route.params.id
  if (platform && id) {
    modpackStore.init(platform, id)
  }
}
</script>

<template>
  <div class="detail-view">
    <div
      v-if="modpackStore.loading && !modpackStore.detail"
      v-loading="true"
      element-loading-text="加载整合包详情中..."
      class="detail-skeleton"
    >
      <ElSkeleton :rows="8" animated />
    </div>

    <div
      v-else-if="modpackStore.error && !modpackStore.detail"
      class="detail-error"
    >
      <ElEmpty :description="modpackStore.error" />
      <div class="detail-actions">
        <ElButton type="primary" @click="retry">重试</ElButton>
        <ElButton @click="goBack">返回</ElButton>
      </div>
    </div>

    <ElEmpty
      v-else-if="!modpackStore.loading && !modpackStore.detail"
      description="未找到该整合包信息"
    />

    <template v-else-if="modpackStore.detail">
      <div class="info-card">
        <div class="info-inner">
          <div class="info-icon">
            <ElAvatar
              v-if="modpackStore.detail.icon_url"
              :src="modpackStore.detail.icon_url"
              :size="72"
              shape="square"
            />
            <ElAvatar
              v-else
              :size="72"
              shape="square"
            >
              📦
            </ElAvatar>
          </div>

          <div class="info-body">
            <div class="info-title-row">
              <h1 class="info-title">{{ modpackStore.detail.name }}</h1>
              <ElTag :type="platformTagType" size="small">{{ platformLabel }}</ElTag>
            </div>

            <div class="info-meta">
              <span v-if="modpackStore.detail.author" class="info-author">
                {{ modpackStore.detail.author }}
              </span>
              <ElDivider v-if="modpackStore.detail.author" direction="vertical" />
              <span class="info-downloads">
                下载量 {{ formatDownloads(modpackStore.detail.download_count) }}
              </span>
              <ElDivider direction="vertical" />
              <a
                v-if="externalUrl"
                :href="externalUrl"
                target="_blank"
                rel="noopener"
                class="info-link"
              >
                原始链接
              </a>
            </div>

            <p v-if="modpackStore.detail.summary" class="info-summary">
              {{ modpackStore.detail.summary }}
            </p>

            <div
              class="info-tags"
              v-if="
                modpackStore.detail.categories?.length ||
                modpackStore.detail.loaders?.length ||
                modpackStore.detail.game_versions?.length
              "
            >
              <ElTag
                v-for="cat in modpackStore.detail.categories"
                :key="'cat-' + cat"
                size="small"
              >
                {{ cat }}
              </ElTag>
              <ElTag
                v-for="loader in modpackStore.detail.loaders"
                :key="'loader-' + loader"
                type="info"
                size="small"
              >
                {{ loader }}
              </ElTag>
              <ElTag
                v-for="ver in modpackStore.detail.game_versions"
                :key="'ver-' + ver"
                type="success"
                size="small"
              >
                {{ ver }}
              </ElTag>
            </div>

            <div v-if="modpackStore.detail.last_updated" class="info-updated">
              更新于 {{ formatDate(modpackStore.detail.last_updated) }}
            </div>
          </div>
        </div>

        <div
          v-if="modpackStore.detail.description"
          class="info-description"
          v-html="modpackStore.detail.description"
        />
      </div>

      <VersionSelector />
      <ModListPreview />
    </template>
  </div>
</template>

<style lang="scss" scoped>
.detail-view {
  padding: var(--notion-spacing-xl);
  max-width: var(--notion-container-max);
  margin: 0 auto;
}

.detail-skeleton {
  min-height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.detail-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--notion-spacing-md);
  padding-top: 80px;
}

.detail-actions {
  display: flex;
  gap: var(--notion-spacing-sm);
}

.info-card {
  background: var(--notion-canvas);
  border-radius: var(--notion-rounded-lg);
  border: 1px solid var(--notion-hairline);
  padding: var(--notion-spacing-xl);
  margin-bottom: var(--notion-spacing-xl);
}

.info-inner {
  display: flex;
  gap: var(--notion-spacing-lg);
  align-items: flex-start;
}

.info-icon {
  flex-shrink: 0;

  :deep(.el-avatar) {
    border-radius: var(--notion-rounded-lg);
  }
}

.info-body {
  flex: 1;
  min-width: 0;
}

.info-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--notion-spacing-xs);
  margin-bottom: var(--notion-spacing-xxs);
}

.info-title {
  font-size: var(--notion-font-size-h5);
  font-weight: $font-weight-semibold;
  color: var(--notion-ink);
  margin: 0;
  line-height: var(--notion-line-height-h5);
  letter-spacing: 0;
}

.info-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--notion-spacing-xxs);
  margin-bottom: var(--notion-spacing-xs);
  color: var(--notion-slate);
  font-size: var(--notion-font-size-caption);

  :deep(.el-divider--vertical) {
    height: 1em;
    margin: 0 var(--notion-spacing-xxs);
    border-left-color: var(--notion-hairline-strong);
  }
}

.info-author {
  color: var(--notion-slate);
}

.info-downloads {
  color: var(--notion-charcoal);
}

.info-link {
  color: var(--notion-link-blue);
  text-decoration: none;

  &:hover {
    text-decoration: underline;
    color: var(--notion-link-blue-pressed);
  }
}

.info-summary {
  margin: 0 0 var(--notion-spacing-sm) 0;
  color: var(--notion-charcoal);
  font-size: var(--notion-font-size-body-sm);
  line-height: var(--notion-line-height-body);
}

.info-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--notion-spacing-xxs);
  margin-bottom: var(--notion-spacing-xs);
}

.info-updated {
  color: var(--notion-steel);
  font-size: var(--notion-font-size-micro);
}

.info-description {
  margin-top: var(--notion-spacing-lg);
  padding-top: var(--notion-spacing-md);
  border-top: 1px solid var(--notion-hairline);
  color: var(--notion-charcoal);
  font-size: var(--notion-font-size-body-sm);
  line-height: 1.8;

  :deep(img) {
    max-width: 100%;
  }

  :deep(a) {
    color: var(--notion-link-blue);
  }

  :deep(h1),
  :deep(h2),
  :deep(h3),
  :deep(h4),
  :deep(h5),
  :deep(h6) {
    color: var(--notion-ink);
  }

  :deep(p),
  :deep(li),
  :deep(span) {
    color: var(--notion-charcoal);
  }

  :deep(table) {
    border-color: var(--notion-hairline);
  }

  :deep(th),
  :deep(td) {
    border-color: var(--notion-hairline);
  }

  :deep(strong),
  :deep(b) {
    color: var(--notion-ink);
  }

  :deep(code) {
    background: var(--notion-surface);
    color: var(--notion-primary);
    padding: 2px 6px;
    border-radius: var(--notion-rounded-xs);
    font-family: 'JetBrains Mono', 'Cascadia Code', 'Consolas', 'Monaco', monospace;
    font-size: 0.9em;
  }
}

@media (max-width: 576px) {
  .detail-view {
    padding: var(--notion-spacing-md);
  }

  .info-inner {
    flex-direction: column;
    align-items: center;
    text-align: center;
  }

  .info-title-row {
    justify-content: center;
  }

  .info-meta {
    justify-content: center;
  }

  .info-tags {
    justify-content: center;
  }
}
</style>
