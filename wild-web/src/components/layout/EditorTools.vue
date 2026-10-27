<template>
  <div class="editor-tools">
    <LLMConfigDialog :visible="ui.modelConfigVisible" @update:visible="ui.modelConfigVisible = $event" />
    <ElDialog v-model="ui.shortcutsVisible" title="快捷键与操作" width="min(520px, calc(100vw - 28px))" append-to-body>
      <dl class="shortcut-list"><template v-for="shortcut in shortcuts" :key="shortcut[0]"><dt>{{ shortcut[0] }}</dt><dd>{{ shortcut[1] }}</dd></template></dl>
      <p class="tool-hint">输入文字时保留输入框自身的快捷键；Ctrl+S 始终保存场景。</p>
    </ElDialog>
  </div>
</template>
<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { ElDialog } from 'element-plus'
import 'element-plus/es/components/dialog/style/css'
import { useUIStore } from '../../stores/uiStore'
const LLMConfigDialog = defineAsyncComponent(() => import('./LLMConfigDialog.vue'))
const ui = useUIStore()
const shortcuts = [['Ctrl / ⌘ + S', '保存到服务器'], ['Ctrl / ⌘ + Z', '撤销'], ['Ctrl / ⌘ + Shift + Z / Y', '重做'], ['Ctrl / ⌘ + B', '收起或展开左侧面板'], ['Alt + 1–7', '切换左侧功能'], ['F', '聚焦选中，无选中时查看全景'], ['Shift + F', '渲染界面全屏'], ['Esc', '取消构件放置 / 退出全屏'], ['Ctrl + 单击', '多选构件'], ['右键单击门窗', '操作支持交互的门窗']]
</script>
<style scoped>
.tool-hint{font-size:10px;line-height:1.8;color:var(--studio-muted);margin-top:10px}.shortcut-list{display:grid;grid-template-columns:auto 1fr;gap:14px;font-size:12px}.shortcut-list dt{font-family:monospace;color:var(--studio-muted)}.shortcut-list dd{color:var(--studio-muted)}
</style>
