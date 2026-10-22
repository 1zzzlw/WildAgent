<template>
  <div class="editor-tools">
    <section class="tool-section">
      <h2>工作台设置 <span>PREFERENCES</span></h2>
      <label class="setting-row">界面动画 <input v-model="ui.animationsEnabled" type="checkbox" /></label>
      <label class="setting-row">操作提示音 <input v-model="ui.soundsEnabled" type="checkbox" /></label>
      <div class="tool-actions"><button type="button" @click="configVisible = true">模型配置</button><button type="button" @click="ui.shortcutsVisible = true">快捷键</button><button type="button" @click="ui.openPanel('aiChat')">会话管理</button></div>
    </section>
    <LLMConfigDialog :visible="configVisible" @update:visible="configVisible = $event" />
    <ElDialog v-model="ui.shortcutsVisible" title="快捷键与操作" width="min(520px, calc(100vw - 28px))" append-to-body>
      <dl class="shortcut-list"><template v-for="shortcut in shortcuts" :key="shortcut[0]"><dt>{{ shortcut[0] }}</dt><dd>{{ shortcut[1] }}</dd></template></dl>
      <p class="tool-hint">输入文字时保留输入框自身的快捷键；Ctrl+S 始终保存场景。</p>
    </ElDialog>
  </div>
</template>
<script setup lang="ts">
import { defineAsyncComponent, ref } from 'vue'
import { ElDialog } from 'element-plus'
import 'element-plus/es/components/dialog/style/css'
import { useUIStore } from '../../stores/uiStore'
const LLMConfigDialog = defineAsyncComponent(() => import('./LLMConfigDialog.vue'))
const ui = useUIStore()
const configVisible = ref(false)
const shortcuts = [['Ctrl / ⌘ + S', '保存到服务器'], ['Ctrl / ⌘ + Z', '撤销'], ['Ctrl / ⌘ + Shift + Z / Y', '重做'], ['Ctrl / ⌘ + B', '收起或展开左侧面板'], ['Alt + 1–8', '切换左侧功能'], ['F', '聚焦选中，无选中时查看全景'], ['Shift + F', '渲染界面全屏'], ['Esc', '退出全屏'], ['Ctrl + 单击', '多选构件'], ['右键单击门窗', '操作支持交互的门窗']]
</script>
<style scoped>
.editor-tools{padding-bottom:18px}.tool-section{padding:18px 16px;border-bottom:1px solid var(--studio-border)}.tool-section h2{display:flex;justify-content:space-between;align-items:center;color:#d6e0e6;font-size:12px;font-weight:550;margin-bottom:14px}.tool-section h2 span{font-size:8px;letter-spacing:1.4px;font-weight:400;color:#687b88}.editor-tools button{display:flex;align-items:center;justify-content:center;gap:7px;min-height:35px;padding:7px 9px;border:1px solid #ffffff15;border-radius:7px;background:#ffffff04;color:#bdcbd4;font-size:11px;cursor:pointer;transition:background .15s,border-color .15s}.editor-tools button:hover:not(:disabled){background:#a6c3b514;border-color:#a6c3b54a}.editor-tools button:disabled{opacity:.35;cursor:not-allowed}.tool-hint{font-size:10px;line-height:1.8;color:#83959f;margin-top:10px}.tool-actions{display:flex;gap:7px;margin-top:12px}.tool-actions>button{flex:1}.setting-row{display:flex;align-items:center;justify-content:space-between;min-height:34px;color:#adbdc7;font-size:11px}.setting-row input{accent-color:var(--studio-accent);width:15px;height:15px}.shortcut-list{display:grid;grid-template-columns:auto 1fr;gap:14px;font-size:12px}.shortcut-list dt{font-family:monospace;color:#a6c3b5}.shortcut-list dd{color:#aabac5}
</style>
