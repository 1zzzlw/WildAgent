<template>
  <main class="visitor-gate">
    <section class="visitor-card" aria-labelledby="visitor-title">
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
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
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
  color: #e5e7eb;
  background:
    radial-gradient(circle at 20% 15%, rgba(14, 99, 156, 0.24), transparent 32%),
    radial-gradient(circle at 80% 85%, rgba(64, 158, 255, 0.14), transparent 30%),
    #151719;
}

.visitor-card {
  width: min(420px, 100%);
  padding: 38px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 14px;
  background: rgba(37, 37, 38, 0.96);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.36);
}

.visitor-brand {
  width: fit-content;
  margin-bottom: 22px;
  padding: 5px 9px;
  border: 1px solid rgba(64, 158, 255, 0.45);
  border-radius: 5px;
  color: #79bbff;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.18em;
}

h1 {
  margin: 0;
  color: #f3f4f6;
  font-size: 26px;
  font-weight: 600;
}

p {
  margin: 10px 0 24px;
  color: #a8abb2;
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
  color: #73767a;
  font-size: 12px;
  line-height: 1.6;
}
</style>
