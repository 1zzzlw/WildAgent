<template>
  <main class="login-page">
    <section class="login-card" aria-labelledby="login-title">
      <button class="theme-button" type="button" :aria-label="theme.isDark ? '切换为亮色主题' : '切换为暗色主题'" @click="theme.toggle()">{{ theme.isDark ? '亮色 ☀' : '暗色 ☾' }}</button>
      <div class="wordmark">WILD <span>建筑蓝图工作台</span></div>
      <div class="building-mark" aria-hidden="true"><i></i><i></i><i></i></div>
      <h1 id="login-title">{{ registering ? '创建你的 WILD 账号' : '走进你的建筑世界' }}</h1>
      <p class="intro">{{ registering ? '从一个想法开始，描绘属于你的建筑世界。' : '登录后编辑与保存蓝图，也可以先以游客身份看看。' }}</p>
      <form v-if="registering" class="register-form" @submit.prevent="registerAccount" @input="error = ''">
        <label for="register-username">用户名</label>
        <input ref="registerUsernameInput" id="register-username" v-model.trim="registration.username" name="username" autocomplete="username" placeholder="怎么称呼你" minlength="2" maxlength="64" pattern=".*\S.*" title="用户名不能只包含空格" :disabled="busy || sendingCode || checking" required />
        <label for="register-email">邮箱</label>
        <input ref="registerEmailInput" id="register-email" v-model.trim="registration.email" name="email" type="email" autocomplete="email" placeholder="请输入邮箱地址" :disabled="busy || sendingCode || checking" required />
        <label for="register-code">邮箱验证码</label>
        <div class="verification-field">
          <input id="register-code" v-model.trim="registration.code" name="verification-code" type="text" inputmode="numeric" autocomplete="one-time-code" placeholder="6 位数字验证码" pattern="[0-9]{6}" maxlength="6" title="请输入 6 位数字验证码" :disabled="busy || sendingCode || checking" required />
          <button class="code-button" type="button" :disabled="busy || sendingCode || checking || codeSeconds > 0" @click="sendVerificationCode">{{ sendingCode ? '发送中…' : codeSeconds > 0 ? codeSeconds + ' 秒后重发' : '获取验证码' }}</button>
        </div>
        <label for="register-password">密码</label>
        <div class="password-field">
          <input id="register-password" v-model="registration.password" name="password" :type="showPassword ? 'text' : 'password'" autocomplete="new-password" placeholder="至少 8 位登录密码" minlength="8" maxlength="128" :disabled="busy || sendingCode || checking" required />
          <button class="password-toggle" type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" :aria-pressed="showPassword" aria-controls="register-password register-confirm-password" :disabled="busy || sendingCode || checking" @click="showPassword = !showPassword">{{ showPassword ? '隐藏' : '显示' }}</button>
        </div>
        <label for="register-confirm-password">确认密码</label>
        <input ref="confirmPasswordInput" id="register-confirm-password" v-model="registration.confirmPassword" name="confirm-password" :type="showPassword ? 'text' : 'password'" autocomplete="new-password" placeholder="请再次输入密码" minlength="8" maxlength="128" :aria-invalid="confirmTouched && passwordMismatch ? true : undefined" :aria-describedby="confirmTouched && passwordMismatch ? 'confirm-password-error' : undefined" :disabled="busy || sendingCode || checking" required @blur="confirmTouched = true" />
        <p v-if="confirmTouched && passwordMismatch" id="confirm-password-error" class="field-error" role="alert">两次输入的密码不一致</p>
        <p v-if="registrationNotice" class="registration-notice" role="status">{{ registrationNotice }}</p>
        <p v-if="error" class="field-error" role="alert">{{ error }}</p>
        <button class="primary-button" type="submit" :disabled="busy || sendingCode || checking">{{ busy ? '正在注册…' : '注册' }}</button>
      </form>
      <form v-else @submit.prevent="signIn(false)">
        <label for="login-email">邮箱</label>
        <input ref="loginEmailInput" id="login-email" v-model.trim="email" name="email" type="email" autocomplete="username" placeholder="请输入注册邮箱" :disabled="busy || checking" required />
        <label for="login-password">密码</label>
        <input id="login-password" v-model="password" name="password" type="password" autocomplete="current-password" placeholder="请输入密码" :disabled="busy || checking" required />
        <p v-if="error" class="login-error" role="alert">{{ error }}</p>
        <button class="primary-button" type="submit" :disabled="busy || checking">{{ checking ? '正在恢复登录…' : busy ? '正在登录…' : '密码登录' }}</button>
      </form>
      <p class="account-switch">
        {{ registering ? '已有账号？' : '还没有账号？' }}
        <button type="button" :disabled="busy || sendingCode || checking" @click="switchMode">{{ registering ? '返回登录' : '立即注册' }}</button>
      </p>
      <template v-if="!registering">
        <div class="divider"><span>或</span></div>
        <button class="guest-button" type="button" :disabled="busy || checking" @click="signIn(true)">游客登录 <span>↗</span></button>
        <p class="guest-note">游客可浏览建筑、体验交互并导出 GLB；编辑、保存和其他导出需密码登录。</p>
      </template>
      <RouterLink class="business-link" to="/business-plan">了解 WILD · 商业介绍 ↗</RouterLink>
      <div class="login-presence"><OnlinePresence /></div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onUnmounted, reactive, ref, watchEffect } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '../../stores/authStore'
import { useThemeStore } from '../../stores/themeStore'
import OnlinePresence from '../../extensions/presence/OnlinePresence.vue'

defineProps<{ checking: boolean }>()
const auth = useAuthStore()
const theme = useThemeStore()
const email = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')
const registering = ref(false)
const registration = reactive({ username: '', email: '', code: '', password: '', confirmPassword: '' })
const registrationNotice = ref('')
const sendingCode = ref(false)
const codeSeconds = ref(0)
let codeTimer: ReturnType<typeof setInterval> | undefined
let mounted = true
onUnmounted(() => { mounted = false; clearInterval(codeTimer) })
const showPassword = ref(false)
const registerUsernameInput = ref<HTMLInputElement>()
const loginEmailInput = ref<HTMLInputElement>()
const registerEmailInput = ref<HTMLInputElement>()
const confirmPasswordInput = ref<HTMLInputElement>()
const confirmTouched = ref(false)
const passwordMismatch = computed(() => !!registration.confirmPassword && registration.password !== registration.confirmPassword)

watchEffect(() => {
  confirmPasswordInput.value?.setCustomValidity(passwordMismatch.value ? '两次输入的密码不一致' : '')
})

async function switchMode() {
  registering.value = !registering.value
  password.value = ''
  registration.password = ''
  registration.confirmPassword = ''
  registration.code = ''
  error.value = ''
  registrationNotice.value = ''
  showPassword.value = false
  confirmTouched.value = false
  await nextTick()
  const input = registering.value ? registerUsernameInput.value : loginEmailInput.value
  input?.focus()
}

async function sendVerificationCode() {
  if (sendingCode.value || codeSeconds.value > 0 || !registerEmailInput.value?.reportValidity()) return
  sendingCode.value = true
  error.value = ''
  registrationNotice.value = ''
  try {
    const result = await auth.sendEmailCode(registration.email)
    if (!mounted) return
    registrationNotice.value = '验证码已发送，请查收邮箱。'
    const retryAt = Date.now() + result.resend_after * 1000
    clearInterval(codeTimer)
    codeSeconds.value = result.resend_after
    codeTimer = setInterval(() => {
      codeSeconds.value = Math.max(0, Math.ceil((retryAt - Date.now()) / 1000))
      if (!codeSeconds.value) clearInterval(codeTimer)
    }, 1000)
  } catch (reason) {
    error.value = reason instanceof Error && reason.message !== 'Failed to fetch' ? reason.message : '发送失败，请检查网络后重试'
  } finally { sendingCode.value = false }
}

async function registerAccount() {
  if (busy.value || sendingCode.value || passwordMismatch.value) return
  busy.value = true
  error.value = ''
  try {
    await auth.register({ username: registration.username, email: registration.email,
      password: registration.password, confirm_password: registration.confirmPassword, code: registration.code })
    registration.password = registration.confirmPassword = registration.code = ''
  } catch (reason) {
    error.value = reason instanceof Error && reason.message !== 'Failed to fetch' ? reason.message : '注册失败，请检查网络后重试'
  } finally { busy.value = false }
}

async function signIn(guest: boolean) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await auth.login(guest ? undefined : email.value, guest ? undefined : password.value)
    password.value = ''
  } catch (reason) {
    error.value = reason instanceof Error && reason.message !== 'Failed to fetch' ? reason.message : '无法连接登录服务，请稍后重试'
  } finally { busy.value = false }
}
</script>

<style scoped>
.login-page{height:100dvh;overflow-y:auto;display:flex;justify-content:center;padding:32px 20px;background:radial-gradient(ellipse at 15% 15%,var(--studio-hover),transparent 55%),var(--studio-bg);color:var(--studio-text)}
.login-card{position:relative;flex-shrink:0;margin:auto 0;width:min(440px,100%);padding:36px 38px 30px;background:var(--studio-surface);border:1px solid var(--studio-border);border-radius:16px;box-shadow:0 24px 80px #183b2910}
.theme-button{position:absolute;right:22px;top:24px;border:1px solid var(--studio-border);border-radius:6px;background:transparent;color:var(--studio-muted);padding:5px 9px;font-size:11px;cursor:pointer}
.wordmark{display:flex;flex-direction:column;gap:5px;font-size:22px;font-weight:700;letter-spacing:4px;color:var(--studio-accent)}.wordmark span{font-size:10px;font-weight:400;letter-spacing:2px;color:var(--studio-muted)}
.login-presence{margin-top:18px;padding-top:18px;border-top:1px solid var(--studio-border)}
.building-mark{height:65px;margin:24px 0 18px;display:flex;align-items:end;gap:7px}.building-mark i{display:block;width:34px;height:43px;border:1px solid var(--studio-accent-border);background:repeating-linear-gradient(0deg,transparent 0 9px,var(--studio-border) 9px 10px),var(--studio-hover);transform:skewY(-12deg)}.building-mark i:nth-child(2){height:65px;width:48px}.building-mark i:nth-child(3){height:30px;width:48px}
h1{font-size:25px;font-weight:600;letter-spacing:-.5px}.intro{margin:10px 0 24px;color:var(--studio-muted);font-size:12px;line-height:1.9}form{display:flex;flex-direction:column;gap:8px}label{font-size:12px;margin-top:5px}input{width:100%;height:42px;border:1px solid var(--studio-border);border-radius:7px;padding:0 12px;background:var(--studio-input);color:var(--studio-text);font:inherit;font-size:13px}input:focus{outline:2px solid var(--studio-accent-border);outline-offset:1px}
.primary-button,.guest-button{width:100%;height:43px;border-radius:7px;font-size:13px;cursor:pointer}.primary-button{margin-top:12px;background:var(--studio-accent);border:1px solid var(--studio-accent);color:var(--studio-surface)}.guest-button{display:flex;align-items:center;justify-content:space-between;padding:0 14px;border:1px solid var(--studio-border);background:var(--studio-hover);color:var(--studio-text)}button:disabled{opacity:.55;cursor:wait}.login-error{color:var(--studio-danger);font-size:12px;line-height:1.6;margin-top:6px}.divider{display:flex;align-items:center;gap:12px;margin:18px 0;color:var(--studio-muted);font-size:11px}.divider:before,.divider:after{content:'';height:1px;flex:1;background:var(--studio-border)}.guest-note{margin-top:11px;color:var(--studio-muted);font-size:11px;line-height:1.9}.business-link{display:inline-block;margin-top:23px;color:var(--studio-accent);font-size:11px;text-underline-offset:5px}
.password-field{position:relative}.password-field input{padding-right:62px}.password-toggle{position:absolute;top:0;right:0;height:100%;min-width:56px;padding:0 12px;border:0;border-radius:0 7px 7px 0;background:transparent;color:var(--studio-accent);font-size:12px;cursor:pointer}.password-toggle:hover{background:var(--studio-hover)}
.verification-field{display:flex;gap:8px}.verification-field input{flex:1;min-width:0}.code-button{flex-shrink:0;min-height:42px;padding:0 12px;border:1px solid var(--studio-accent-border);border-radius:7px;background:var(--studio-hover);color:var(--studio-accent);font-size:12px;cursor:pointer}.code-button:hover{border-color:var(--studio-accent)}.field-error{color:var(--studio-danger);font-size:12px;line-height:1.6}input[aria-invalid="true"]{border-color:var(--studio-danger)}
.account-switch{display:flex;justify-content:center;align-items:center;gap:5px;margin-top:16px;color:var(--studio-muted);font-size:12px}.account-switch button{min-height:32px;padding:4px 5px;border:0;border-radius:4px;background:transparent;color:var(--studio-accent);font-size:12px;cursor:pointer}.account-switch button:hover{text-decoration:underline;text-underline-offset:4px}.registration-notice{padding:10px 12px;margin-top:6px;border:1px solid var(--studio-accent-border);border-radius:7px;background:var(--studio-hover);color:var(--studio-text);font-size:12px;line-height:1.7}
@media(max-width:480px){.login-page{padding:20px 16px}.login-card{padding:28px 24px}.building-mark{margin-top:20px}h1{font-size:23px}.register-form input{height:44px;font-size:16px}.register-form .primary-button{height:44px}.account-switch button{min-height:44px}}
</style>
