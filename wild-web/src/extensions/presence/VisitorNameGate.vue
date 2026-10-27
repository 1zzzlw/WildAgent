<template>
  <main class="visitor-gate">
    <section class="visitor-card" aria-labelledby="visitor-title">
      <button class="gate-theme-toggle" type="button" :aria-label="theme.isDark ? '切换为亮色主题' : '切换为暗色主题'" @click="theme.toggle()">{{ theme.isDark ? '亮色 ☀' : '暗色 ☾' }}</button>
      <div class="visitor-brand">WILD</div>
      <h1 id="visitor-title">进入协作空间</h1>
      <p>输入一个方便同事识别的访客名称。</p>

      <form @submit.prevent="confirmName">
        <el-input
          v-model="name"
          autofocus
          clearable
          :maxlength="MAX_VISITOR_NAME_LENGTH"
          show-word-limit
          placeholder="例如：张工"
          size="large"
          aria-label="访客名称"
        />
        <el-button
          class="enter-button"
          type="primary"
          size="large"
          native-type="submit"
          :disabled="!normalizedName"
        >
          进入编辑器
        </el-button>
      </form>

      <div class="visitor-note">名称仅用于在线列表展示，不是账号，也不会用于会话隔离。</div>
      <RouterLink class="business-plan-entry" to="/business-plan">了解 WILD · 商业计划书 ↗</RouterLink>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useThemeStore } from '../../stores/themeStore'
const theme = useThemeStore()
import { MAX_VISITOR_NAME_LENGTH } from './types'
import { normalizeVisitorName, usePresenceStore } from './store'

const emit = defineEmits<{ confirmed: [] }>()
const presenceStore = usePresenceStore()
const name = ref('')
const normalizedName = computed(() => normalizeVisitorName(name.value))

function confirmName() {
  if (!presenceStore.setVisitorName(normalizedName.value)) return
  emit('confirmed')
}
</script>

<style scoped>
.visitor-gate {
  width: 100vw;
  height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  color: var(--studio-text);
  background: var(--studio-bg);
}

.visitor-card {
  position: relative;
  width: min(420px, 100%);
  padding: 38px;
  border: 1px solid var(--studio-border);
  border-radius: 5px;
  background: var(--studio-surface);
  box-shadow: 0 24px 70px rgba(41, 76, 61, 0.12);
}
.gate-theme-toggle { position: absolute; top: 18px; right: 18px; border: 1px solid var(--studio-border); border-radius: 3px; padding: 4px 9px; color: var(--studio-muted); background: transparent; font-size: 11px; cursor: pointer }
.business-plan-entry { display: inline-block; margin-top: 22px; color: var(--studio-accent); font-size: 12px; text-underline-offset: 5px }

.visitor-brand {
  width: fit-content;
  margin-bottom: 22px;
  padding: 5px 9px;
  border: 1px solid var(--studio-accent-border);
  border-radius: 5px;
  color: var(--studio-accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.18em;
}

h1 {
  margin: 0;
  color: var(--studio-text);
  font-size: 26px;
  font-weight: 600;
}

p {
  margin: 10px 0 24px;
  color: var(--studio-muted);
  font-size: 14px;
  line-height: 1.6;
}

form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.enter-button {
  width: 100%;
}

.visitor-note {
  margin-top: 18px;
  color: var(--studio-muted);
  font-size: 12px;
  line-height: 1.6;
}
</style>
