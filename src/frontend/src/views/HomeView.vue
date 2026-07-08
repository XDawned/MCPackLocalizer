<script setup>
import { useRouter } from 'vue-router'
import { ElButton } from 'element-plus'

const router = useRouter()
</script>

<template>
  <div class="home-view">
    <!-- ═══════ Hero Band Dark ═══════ -->
    <section class="hero-band">
      <div class="hero-glow" />
      <h1 class="hero-headline">MCPackLocalizer</h1>
      <p class="hero-subtitle">Minecraft 整合包本地化工具</p>
      <div class="hero-actions">
        <ElButton
          type="primary"
          size="large"
          class="hero-cta"
          @click="router.push('/local-import')"
        >
          <svg class="cta-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
          <span>本地生成</span>
        </ElButton>
        <ElButton
          type="primary"
          size="large"
          class="hero-cta hero-cta--secondary"
          @click="router.push('/search')"
        >
          <svg class="cta-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
          <span>在线搜索</span>
        </ElButton>
      </div>
    </section>

    <!-- ═══════ Stats Row ═══════ -->
    <section class="stats-row">
      <div class="stat-card">
        <div class="stat-icon-wrap">
          <svg class="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" />
            <path d="M2 12h20" />
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
          </svg>
        </div>
        <span class="stat-label">CurseForge + Modrinth</span>
      </div>
      <div class="stat-card">
        <div class="stat-icon-wrap">
          <svg class="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
        </div>
        <span class="stat-label">多 AI 提供商</span>
      </div>
      <div class="stat-card">
        <div class="stat-icon-wrap">
          <svg class="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m5 8 6 6" />
            <path d="m4 14 6-6 2 2" />
            <path d="M2 5h12" />
            <path d="M7 2h1" />
            <path d="m22 22-5-5" />
            <path d="M14 18V8" />
            <path d="m18 14 4 4" />
          </svg>
        </div>
        <span class="stat-label">术语库驱动</span>
      </div>
    </section>

    <!-- ═══════ Feature Cards ═══════ -->
    <section class="feature-cards">
      <div class="feature-grid">
        <div class="feature-card feature-card--mint" @click="router.push('/local-import')">
          <div class="feature-card-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
            </svg>
          </div>
          <h3 class="feature-card-title">从本地导入</h3>
          <p class="feature-card-desc">选择本地整合包目录，自动识别格式并检测待翻译内容</p>
        </div>

        <div class="feature-card feature-card--lavender" @click="router.push('/search')">
          <div class="feature-card-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
          </div>
          <h3 class="feature-card-title">整合包检索</h3>
          <p class="feature-card-desc">对接 CurseForge 和 Modrinth，多维度搜索与筛选，快速找到目标整合包</p>
        </div>

        <div class="feature-card feature-card--sky">
          <div class="feature-card-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
          </div>
          <h3 class="feature-card-title">AI 翻译工作流</h3>
          <p class="feature-card-desc">多 AI 提供商支持，术语库驱动，可视化进度追踪</p>
        </div>
      </div>
    </section>
  </div>
</template>

<style lang="scss" scoped>
/* ── Layout ─────────────────────────────────────────── */
.home-view {
  max-width: var(--notion-container-max);
  margin: 0 auto;
  padding: 1px 0;
}

/* ── Hero Band Dark ─────────────────────────────────── */
.hero-band {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  background-image: url('@/assets/home.jpg');
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  border-radius: var(--notion-rounded-lg);
  padding: var(--notion-spacing-hero) var(--notion-spacing-xxl);
  margin: 0 calc(-1 * 24px);
  min-height: 480px;
  overflow: hidden;
}

.hero-glow {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 480px;
  height: 480px;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: radial-gradient(circle, rgba(86, 69, 212, 0.13) 0%, rgba(86, 69, 212, 0.04) 45%, transparent 70%);
  pointer-events: none;
  animation: hero-glow-pulse 4s ease-in-out infinite;
}

@keyframes hero-glow-pulse {
  0%, 100% { opacity: 0.6; transform: translate(-50%, -50%) scale(1); }
  50% { opacity: 1; transform: translate(-50%, -50%) scale(1.08); }
}

.hero-headline {
  font-family: var(--notion-font-sans);
  font-size: var(--notion-font-size-h1);
  font-weight: 600;
  line-height: var(--notion-line-height-h1);
  letter-spacing: var(--notion-ls-h1);
  color: var(--notion-on-dark);
  margin-bottom: var(--notion-spacing-md);
  position: relative;
  animation: fadeInUp 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}

.hero-subtitle {
  font-family: var(--notion-font-sans);
  font-size: var(--notion-font-size-subtitle);
  font-weight: 400;
  line-height: var(--notion-line-height-body);
  color: var(--notion-on-dark);
  margin-bottom: var(--notion-spacing-xxxl);
  animation: fadeInUp 0.7s 0.1s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}

.hero-actions {
  animation: fadeInUp 0.7s 0.2s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}

.hero-cta {
  --el-button-bg-color: var(--notion-primary);
  --el-button-border-color: var(--notion-primary);
  --el-button-hover-bg-color: var(--notion-primary-pressed);
  --el-button-hover-border-color: var(--notion-primary-pressed);
  --el-button-active-bg-color: var(--notion-primary-deep);
  --el-button-active-border-color: var(--notion-primary-deep);
  --el-button-text-color: var(--notion-on-primary);
  --el-button-hover-text-color: var(--notion-on-primary);
  --el-button-active-text-color: var(--notion-on-primary);

  font-family: var(--notion-font-sans);
  font-size: var(--notion-font-size-body-sm);
  font-weight: 500;
  border-radius: var(--notion-rounded-md);
  padding: 10px 22px;
  height: auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.hero-cta--secondary {
  --el-button-bg-color: rgba(255, 255, 255, 0.2);
  --el-button-border-color: rgba(255, 255, 255, 0.35);
  --el-button-hover-bg-color: rgba(255, 255, 255, 0.3);
  --el-button-hover-border-color: rgba(255, 255, 255, 0.5);
  --el-button-active-bg-color: rgba(255, 255, 255, 0.25);
  --el-button-active-border-color: rgba(255, 255, 255, 0.45);
  --el-button-text-color: var(--notion-on-dark);
  --el-button-hover-text-color: var(--notion-on-dark);
  --el-button-active-text-color: var(--notion-on-dark);
}

.cta-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  margin-right: var(--notion-spacing-xxs);
}

/* ── Stats Row ──────────────────────────────────────── */
.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--notion-spacing-md);
  margin-top: var(--notion-spacing-xxl);
  margin-bottom: var(--notion-spacing-section-sm);

  @media (max-width: 640px) {
    grid-template-columns: 1fr;
  }
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background-color: var(--notion-surface);
  border-radius: var(--notion-rounded-lg);
  padding: var(--notion-spacing-lg) var(--notion-spacing-xl);
  transition: transform var(--notion-transition-normal), box-shadow var(--notion-transition-normal);
  animation: fadeInUp 0.5s 0.3s ease both;

  &:nth-child(2) { animation-delay: 0.4s; }
  &:nth-child(3) { animation-delay: 0.5s; }

  &:hover {
    transform: translateY(-2px);
    box-shadow: var(--notion-shadow-card);
  }
}

.stat-icon-wrap {
  width: 40px;
  height: 40px;
  border-radius: var(--notion-rounded-sm);
  background-color: var(--notion-tint-lavender);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-icon {
  width: 22px;
  height: 22px;
  color: var(--notion-primary);
}

.stat-label {
  font-size: var(--notion-font-size-body-sm);
  font-weight: 500;
  color: var(--notion-ink);
  white-space: nowrap;
}

/* ── Feature Cards ──────────────────────────────────── */
.feature-cards {
  margin-top: var(--notion-spacing-section-sm);
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--notion-spacing-lg);

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
}

.feature-card {
  border-radius: var(--notion-rounded-lg);
  padding: var(--notion-spacing-xxl);
  cursor: pointer;
  transition: transform var(--notion-transition-normal), box-shadow var(--notion-transition-normal);
  animation: fadeInUp 0.5s 0.5s ease both;

  &:nth-child(2) { animation-delay: 0.6s; }
  &:nth-child(3) { animation-delay: 0.7s; }

  &:hover {
    transform: translateY(-4px);
    box-shadow: var(--notion-shadow-card);
  }
}

.feature-card--mint {
  background-color: var(--notion-tint-mint);
}

.feature-card--lavender {
  background-color: var(--notion-tint-lavender);
}

.feature-card--sky {
  background-color: var(--notion-tint-sky);
}

.feature-card-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--notion-rounded-sm);
  background-color: var(--notion-canvas);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--notion-spacing-lg);

  svg {
    width: 28px;
    height: 28px;
    color: var(--notion-primary);
  }
}

.feature-card-title {
  font-family: var(--notion-font-sans);
  font-size: var(--notion-font-size-h5);
  font-weight: 600;
  line-height: var(--notion-line-height-h5);
  color: var(--notion-charcoal);
  margin-bottom: var(--notion-spacing-xs);
}

.feature-card-desc {
  font-family: var(--notion-font-sans);
  font-size: var(--notion-font-size-body-sm);
  font-weight: 400;
  line-height: var(--notion-line-height-body-sm);
  color: var(--notion-slate);
  margin: 0;
}

/* ── Shared Keyframe ────────────────────────────────── */
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ── Responsive Hero ────────────────────────────────── */
@media (max-width: 768px) {
  .hero-band {
    padding: var(--notion-spacing-section-lg) var(--notion-spacing-xl);
    min-height: 360px;
  }

  .hero-headline {
    font-size: var(--notion-font-size-h2);
  }

  .hero-subtitle {
    font-size: var(--notion-font-size-body);
  }
}

@media (max-width: 480px) {
  .hero-band {
    padding: var(--notion-spacing-section) var(--notion-spacing-lg);
    min-height: 280px;
  }

  .hero-headline {
    font-size: var(--notion-font-size-h3);
  }

  .hero-subtitle {
    font-size: var(--notion-font-size-body-sm);
  }
}
</style>
