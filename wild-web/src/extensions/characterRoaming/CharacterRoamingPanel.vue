<template>
  <div class="character-roaming">
    <button v-if="!roaming.active" class="roaming-launch" type="button" @click="roaming.start()">
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="4" r="2.3" /><path d="M12 7v7m-5-4 5-2 5 2m-5 4-4 7m4-7 4 7" /></svg>
      <span>人物漫游</span>
    </button>
    <section v-else class="roaming-panel" aria-label="人物漫游控制">
      <div class="roaming-heading"><strong>机器人漫游</strong><span>{{ roaming.view === 'first' ? '第一视角' : '第三视角' }}</span></div>
      <p>W A S D 移动 · 空格跳跃 · 鼠标转向</p>
      <p>F5 切换视角 · 右键交互 · Esc 释放鼠标</p>
      <div class="roaming-actions">
        <button v-if="!roaming.locked" type="button" @click="roaming.capture()">继续漫游</button>
        <button type="button" @click="roaming.toggleView()">切换视角</button>
        <button type="button" @click="roaming.stop()">退出漫游</button>
      </div>
      <p v-if="!roaming.locked" class="roaming-hint">点击画面进入控制，释放鼠标后可操作面板。</p>
      <p v-if="roaming.message" class="roaming-message" role="status">{{ roaming.message }}</p>
    </section>
  </div>
  <div v-if="roaming.active && roaming.locked" class="roaming-crosshair" :class="{ interactable: roaming.interactionLabel }" aria-hidden="true"></div>
  <div v-if="roaming.active && roaming.locked && roaming.interactionLabel" class="roaming-target" role="status">{{ roaming.interactionLabel }}</div>
</template>

<script setup lang="ts">
import { useCharacterRoamingStore } from './store'
const roaming = useCharacterRoamingStore()
</script>

<style scoped>
.character-roaming{position:absolute;right:16px;top:62px;z-index:44;pointer-events:none;color:#e3ece8;font-size:12px}
.roaming-launch,.roaming-panel{pointer-events:auto;border:1px solid #ffffff30;background:#172a30bf;backdrop-filter:blur(14px);box-shadow:0 5px 24px #0002;border-radius:12px}
.roaming-launch{display:flex;align-items:center;gap:7px;padding:9px 12px;color:inherit;font:inherit;cursor:pointer}
.roaming-launch svg{width:19px;height:22px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
.roaming-launch:hover{background:#34564be0;border-color:#a6dbbe8a}
.roaming-panel{padding:13px 15px;max-width:320px}
.roaming-heading{display:flex;align-items:center;justify-content:space-between;gap:24px}.roaming-heading span{color:#a6dfc6;font-size:11px}
.roaming-panel p{margin:9px 0 0;line-height:1.6;font-size:11px;color:#b4c6cb}
.roaming-actions{display:flex;gap:8px;margin-top:12px}.roaming-actions button{border:1px solid #ffffff2e;border-radius:7px;background:#ffffff0b;color:inherit;padding:7px 10px;font:inherit;cursor:pointer}.roaming-actions button:hover{background:#8bc5ac32}
.roaming-panel .roaming-hint{color:#a6dfc6}.roaming-panel .roaming-message{color:#efcd9d}
.roaming-crosshair{position:absolute;left:50%;top:50%;width:5px;height:5px;transform:translate(-50%,-50%);border:1px solid #ffffffdf;border-radius:50%;box-shadow:0 0 3px #000;pointer-events:none;z-index:46}
.roaming-crosshair.interactable{width:11px;height:11px;border-color:#a1f3cc;box-shadow:0 0 8px #72cda878}
.roaming-target{position:absolute;left:50%;top:calc(50% + 25px);transform:translateX(-50%);padding:7px 12px;border-radius:8px;color:#e7fff3;background:#173c32bb;font-size:12px;pointer-events:none;z-index:46;white-space:nowrap}
@media(max-width:760px){.character-roaming{right:10px}.roaming-panel{max-width:245px;padding:11px}.roaming-actions{gap:5px}.roaming-actions button{padding:7px}}
</style>
