<template>
  <div class="top-bar">
    <div class="toolbar-section">
      <el-button class="toolbar-btn" size="small" @click="handleNew" title="新建场景">
        <span>新建</span>
      </el-button>
      <el-button class="toolbar-btn" size="small" @click="handleOpen" title="打开场景">
        <span>打开</span>
      </el-button>
      <el-button class="toolbar-btn save-btn" type="primary" size="small" @click="handleSave"
        :loading="isSaving" :disabled="!sceneStore.document?.dirty || isSaving" title="保存到服务器">
        <span>{{ isSaving ? '保存中' : '保存' }}</span>
      </el-button>
      <el-button class="toolbar-btn" size="small" @click="handleExport" title="导出 .wild 文件">
        <span>导出</span>
      </el-button>
    </div>

    <div class="toolbar-section">
      <el-button class="toolbar-btn" size="small" @click="handleUndo" :disabled="!historyStore.canUndo" title="撤销">
        <span>撤销</span>
      </el-button>
      <el-button class="toolbar-btn" size="small" @click="handleRedo" :disabled="!historyStore.canRedo" title="重做">
        <span>重做</span>
      </el-button>
    </div>

    <div class="toolbar-section">
      <el-button class="toolbar-btn" size="small" @click="handleValidate" title="运行校验">
        <span>校验</span>
      </el-button>
    </div>

    <div class="toolbar-section">
      <el-button class="toolbar-btn" size="small" @click="handleToggleAIPanel" title="切换 AI 对话面板">
        <span>{{ uiStore.bottomPanelVisible ? '隐藏 AI' : '显示 AI' }}</span>
      </el-button>
    </div>

    <div class="toolbar-section">
      <el-button class="toolbar-btn help-entry-btn" size="small" @click="openHelp('guide')" title="查看项目介绍与使用方式">
        <span>项目介绍</span>
      </el-button>
      <el-button class="toolbar-btn help-entry-btn" size="small" @click="openHelp('changelog')" title="查看最近更新">
        <span>更新日志</span>
      </el-button>
    </div>

    <div class="scene-info">
      <span v-if="sceneStore.document">
        {{ sceneStore.document.name }}
        <span v-if="sceneStore.document.dirty" class="dirty-indicator">*</span>
      </span>
    </div>

    <OnlinePresence />

    <el-dialog
      v-model="helpVisible"
      :title="helpSection === 'guide' ? 'WILD 项目介绍与快速上手' : 'WILD 更新日志'"
      width="min(760px, 92vw)"
      class="help-dialog"
      modal-class="wild-help-overlay"
      top="7vh"
      append-to-body
      destroy-on-close
    >
      <div v-if="helpSection === 'guide'" class="help-content">
        <p class="help-lead">
          WILD 是面向建筑蓝图生成、组件编辑和 PBR 材质复用的 AI 三维编辑器。建筑结构由 Blueprint 保存，AI 修改也会经过校验后再进入场景。
        </p>

        <section>
          <h3>推荐工作方式</h3>
          <ol>
            <li><strong>复杂建筑优先选择“精密模式”</strong>：适合多层、高层、复杂屋顶和严格尺寸要求，生成时间更长，但会执行完整规划、组件生成和校验修复。</li>
            <li>在对话中明确建筑尺寸、层数、结构体系、门窗规律、立面构件与屋顶形式；已有场景需要修改时，先选中对象再描述修改目标。</li>
            <li>生成完成后点击顶部“校验”，确认没有结构、引用或材质错误，再保存或导出。</li>
          </ol>
        </section>

        <section>
          <h3>素材库</h3>
          <ul>
            <li>一个素材只需上传一张 Base Color 图片；Normal、Roughness、Metalness 和 AO 为可选通道。</li>
            <li>可设置颜色、粗糙度、金属度、法线强度、真实尺寸和 UV 比例。</li>
            <li>入库素材会保存在本地素材库，之后可以直接复用，也可供 AI 在生成材质方案时自动匹配。</li>
            <li>应用素材前可先选中构件；相同图片会按内容去重，避免重复入库。</li>
          </ul>
        </section>

        <section>
          <h3>组件库与选择</h3>
          <ul>
            <li>组件库可添加门、窗、阳台、雨棚、栏杆、灯具等组合组件；渲染前会统一展开为基础几何。</li>
            <li><kbd>Ctrl</kbd> + 鼠标左键可以连续多选，点击空白处可取消选择和高亮。</li>
            <li>批量导入或操作时会以当前全部选中对象为范围，不需要逐个重复设置。</li>
          </ul>
        </section>

        <section>
          <h3>场景互动</h3>
          <ul>
            <li>对支持交互的门窗或灯具使用鼠标右键，可以触发开合或开关操作。</li>
            <li>灯泡采用玻璃外壳和发光内芯；右键灯泡可在关闭、低亮和高亮之间循环。</li>
            <li>交互只是运行时状态，不会破坏 Blueprint 中的建筑结构。</li>
          </ul>
        </section>

        <div class="help-tip">提示：复杂建筑失败时，请保留生成说明、校验步骤和错误日志，它们可以帮助把问题归类为通用规则并持续提高稳定性。</div>
      </div>

      <div v-else class="help-content changelog">
        <section>
          <div class="release-title"><strong>近期更新</strong><span>当前开发版</span></div>
          <ul>
            <li>新增组件材质语义默认值：门窗、凸窗、栏杆、阳台、雨棚等不再因材质缺失显示为统一白色。</li>
            <li>灯泡升级为透明玻璃外壳与独立发光内芯，并保留右键三档灯光互动。</li>
            <li>完善 PBR 素材入库与复用：支持单图导入、颜色调整、法线强度、真实尺寸和多个可选纹理通道。</li>
            <li>新增 Ctrl + 左键多选、空白处取消选择，以及选中组件批量处理能力。</li>
            <li>增强复杂建筑的通用校验与修复：按结构、坐标、宿主、覆盖、设计约束等类别处理，减少单建筑补丁和无效重试。</li>
            <li>修复工具调用返回列表时触发的 <code>list object has no attribute values</code> 容器兼容错误。</li>
            <li>改进高层住宅塔楼生成约束、标准层复用、核心筒、剪力墙与规则立面表达。</li>
            <li>补充程序化建筑材质扩展方案，为无图片红砖、风化、盐碱和砖缝凹陷效果预留统一架构。</li>
          </ul>
        </section>

        <section>
          <div class="release-title"><strong>稳定性原则</strong></div>
          <p>所有建筑问题优先映射到有限的通用类别，通过共享校验器、确定性修复、协议约束和参数化测试解决，不按建筑名称或组件 ID 堆叠永久补丁。</p>
        </section>
      </div>

      <template #footer>
        <el-button type="primary" @click="helpVisible = false">知道了</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { agentBridge } from '../../agent/agentBridge'
import { useAgentStore } from '../../stores/agentStore'
import { useSceneStore } from '../../stores/sceneStore'
import { useHistoryStore } from '../../stores/historyStore'
import { useUIStore } from '../../stores/uiStore'
import OnlinePresence from '../../extensions/presence/OnlinePresence.vue'

const sceneStore = useSceneStore()
const historyStore = useHistoryStore()
const uiStore = useUIStore()
const agentStore = useAgentStore()
const isSaving = ref(false)
const helpVisible = ref(false)
const helpSection = ref<'guide' | 'changelog'>('guide')

function openHelp(section: 'guide' | 'changelog') {
  helpSection.value = section
  helpVisible.value = true
}

async function handleNew() {
  try {
    await ElMessageBox.confirm('创建新场景将清空当前内容，是否继续？', '确认操作', {
      confirmButtonText: '继续',
      cancelButtonText: '取消',
      type: 'warning'
    })

    const doc = sceneStore.createEmptyDocument()
    sceneStore.loadBlueprint(doc.blueprint, doc.name)
    historyStore.clear()
  } catch {
    // 用户取消
  }
}

function handleOpen() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.wild,.json'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (file) {
      const text = await file.text()
      try {
        const blueprint = JSON.parse(text)
        sceneStore.loadBlueprint(blueprint, file.name)
        historyStore.clear()
      } catch {
        ElMessage.error('文件格式错误')
      }
    }
  }
  input.click()
}

async function handleSave() {
  if (!sceneStore.document || !agentStore.currentSessionId) {
    ElMessage.error('当前场景没有对应的服务器会话，无法保存')
    return
  }
  const issues = sceneStore.validate()
  if (issues.some(issue => issue.level === 'error')) {
    ElMessage.error('场景校验存在错误，请修复后再保存')
    return
  }

  isSaving.value = true
  const saved = await agentBridge.syncBlueprintToBackend(
    sceneStore.document.blueprint as unknown as Record<string, unknown>,
  )
  isSaving.value = false
  if (!saved) {
    ElMessage.error('保存到服务器失败，本地草稿仍然保留')
    return
  }

  const blueprint = sceneStore.document.blueprint
  const elementsCount = (blueprint.geometry.elements?.length || 0)
  const componentsCount = (blueprint.geometry.components?.length || 0)
  agentStore.updateSessionInfo(
    agentStore.currentSessionId,
    blueprint.meta.name || sceneStore.document.name,
    elementsCount + componentsCount,
    componentsCount,
  )
  sceneStore.markSaved()
  ElMessage.success('场景已保存到服务器')
}

function handleExport() {
  const content = sceneStore.exportWild()
  const blob = new Blob([content], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${sceneStore.document?.name || 'scene'}.wild`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出当前草稿，服务端文件未修改')
}

async function handleUndo() {
  const entry = historyStore.undo()
  if (entry) {
    await sceneStore.restoreBlueprint(entry.before)
  }
}

async function handleRedo() {
  const entry = historyStore.redo()
  if (entry) {
    await sceneStore.restoreBlueprint(entry.after)
  }
}

function handleValidate() {
  sceneStore.validate()
}

function handleToggleAIPanel() {
  uiStore.toggleBottomPanel()
}
</script>

<style scoped>
.top-bar {
  height: 48px;
  background: #2d2d30;
  border-bottom: 1px solid #3e3e42;
  display: flex;
  align-items: center;
  padding: 0 12px;
  gap: 16px;
}

.toolbar-section {
  display: flex;
  gap: 4px;
}

.toolbar-btn {
  height: 32px;
  padding: 0 12px;
  background: transparent;
  border: 1px solid #3e3e42;
  color: #cccccc;
  cursor: pointer;
  font-size: 13px;
  border-radius: 3px;
  transition: all 0.15s;
}

.toolbar-btn:hover:not(:disabled) {
  background: #3e3e42;
  border-color: #4e4e52;
}

.save-btn:not(:disabled) {
  border-color: #168bc2;
  background: #137fac;
  color: #ffffff;
}

.save-btn:hover:not(:disabled) {
  border-color: #35bfe8;
  background: #1593c7;
}

.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.scene-info {
  margin-left: auto;
  font-size: 13px;
  color: #cccccc;
}

.dirty-indicator {
  color: #f48771;
  margin-left: 4px;
}

.help-entry-btn {
  border-color: rgba(70, 176, 218, 0.38);
  color: #bdefff;
}

.help-entry-btn:hover:not(:disabled) {
  border-color: rgba(84, 200, 241, 0.72);
  background: rgba(31, 142, 184, 0.18);
  color: #ffffff;
}

</style>

<style>
.wild-help-overlay {
  background: rgba(8, 12, 18, 0.7) !important;
  backdrop-filter: blur(5px);
}

.wild-help-overlay .help-dialog {
  --el-dialog-bg-color: #202227;
  --el-text-color-primary: #eceff4;
  overflow: hidden;
  border: 1px solid rgba(116, 137, 163, 0.28);
  border-radius: 14px;
  background:
    radial-gradient(circle at 100% 0, rgba(31, 142, 184, 0.16), transparent 34%),
    #202227;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.52), 0 0 0 1px rgba(255, 255, 255, 0.025);
}

.wild-help-overlay .help-dialog .el-dialog__header {
  position: relative;
  margin: 0;
  padding: 22px 60px 18px 26px;
  border-bottom: 1px solid rgba(113, 130, 151, 0.2);
}

.wild-help-overlay .help-dialog .el-dialog__header::after {
  position: absolute;
  bottom: -1px;
  left: 26px;
  width: 72px;
  height: 2px;
  border-radius: 2px;
  background: linear-gradient(90deg, #35bfe8, #6d8cff);
  content: '';
}

.wild-help-overlay .help-dialog .el-dialog__title {
  color: #f7f9fc;
  font-size: 19px;
  font-weight: 650;
  letter-spacing: 0.02em;
}

.wild-help-overlay .help-dialog .el-dialog__headerbtn {
  top: 15px;
  right: 16px;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  transition: background 0.16s ease;
}

.wild-help-overlay .help-dialog .el-dialog__headerbtn:hover {
  background: rgba(255, 255, 255, 0.08);
}

.wild-help-overlay .help-dialog .el-dialog__close {
  color: #aeb7c4;
  font-size: 20px;
}

.wild-help-overlay .help-dialog .el-dialog__headerbtn:hover .el-dialog__close {
  color: #ffffff;
}

.wild-help-overlay .help-dialog .el-dialog__body {
  padding: 22px 26px 10px;
}

.wild-help-overlay .help-content {
  max-height: 62vh;
  overflow-y: auto;
  padding: 0 8px 8px 0;
  color: #cbd1db;
  font-size: 14px;
  line-height: 1.72;
  scrollbar-color: #566170 transparent;
  scrollbar-width: thin;
}

.wild-help-overlay .help-content::-webkit-scrollbar {
  width: 7px;
}

.wild-help-overlay .help-content::-webkit-scrollbar-thumb {
  border-radius: 8px;
  background: #566170;
}

.wild-help-overlay .help-content section {
  padding: 16px 18px;
  border: 1px solid rgba(112, 129, 151, 0.18);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.026);
  transition: border-color 0.16s ease, background 0.16s ease;
}

.wild-help-overlay .help-content section:hover {
  border-color: rgba(73, 174, 215, 0.28);
  background: rgba(255, 255, 255, 0.038);
}

.wild-help-overlay .help-content section + section {
  margin-top: 12px;
}

.wild-help-overlay .help-content h3 {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 0 0 10px;
  color: #f4f6fa;
  font-size: 15px;
  font-weight: 650;
}

.wild-help-overlay .help-content h3::before {
  width: 5px;
  height: 15px;
  border-radius: 4px;
  background: linear-gradient(180deg, #45c7ed, #647cff);
  content: '';
}

.wild-help-overlay .help-content p,
.wild-help-overlay .help-content ul,
.wild-help-overlay .help-content ol {
  margin: 0;
}

.wild-help-overlay .help-content ul,
.wild-help-overlay .help-content ol {
  padding-left: 21px;
}

.wild-help-overlay .help-content li {
  padding-left: 3px;
}

.wild-help-overlay .help-content li + li {
  margin-top: 7px;
}

.wild-help-overlay .help-content li::marker {
  color: #4fc3e8;
}

.wild-help-overlay .help-content strong {
  color: #f3f6fa;
  font-weight: 650;
}

.wild-help-overlay .help-lead {
  position: relative;
  margin-bottom: 14px !important;
  padding: 15px 17px 15px 19px;
  overflow: hidden;
  border: 1px solid rgba(72, 185, 226, 0.25);
  border-radius: 10px;
  background: linear-gradient(120deg, rgba(38, 139, 177, 0.16), rgba(70, 91, 150, 0.1));
  color: #e5f6fc;
}

.wild-help-overlay .help-lead::before {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 3px;
  background: #42c3e9;
  content: '';
}

.wild-help-overlay .help-tip {
  margin-top: 14px;
  padding: 12px 15px;
  border: 1px solid rgba(72, 185, 226, 0.2);
  border-radius: 9px;
  background: rgba(39, 154, 196, 0.1);
  color: #bceaf7;
}

.wild-help-overlay .release-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 11px;
  color: #ffffff;
  font-size: 15px;
}

.wild-help-overlay .release-title span {
  padding: 2px 9px;
  border: 1px solid rgba(88, 203, 239, 0.24);
  border-radius: 999px;
  background: rgba(28, 141, 183, 0.2);
  color: #9fe6f8;
  font-size: 11px;
  font-weight: 500;
}

.wild-help-overlay kbd,
.wild-help-overlay code {
  padding: 2px 6px;
  border: 1px solid #4e5967;
  border-radius: 5px;
  background: #15171b;
  box-shadow: inset 0 -1px 0 rgba(255, 255, 255, 0.06);
  color: #eef4fa;
  font-family: Consolas, monospace;
  font-size: 0.9em;
}

.wild-help-overlay .help-dialog .el-dialog__footer {
  padding: 14px 26px 20px;
  border-top: 1px solid rgba(113, 130, 151, 0.14);
}

.wild-help-overlay .help-dialog .el-dialog__footer .el-button--primary {
  min-width: 92px;
  border: 0;
  border-radius: 7px;
  background: linear-gradient(135deg, #168fbe, #3b76ce);
  box-shadow: 0 6px 18px rgba(24, 127, 174, 0.25);
}

.wild-help-overlay .help-dialog .el-dialog__footer .el-button--primary:hover {
  filter: brightness(1.1);
}

@media (max-width: 680px) {
  .wild-help-overlay .help-dialog .el-dialog__header {
    padding: 18px 52px 15px 18px;
  }

  .wild-help-overlay .help-dialog .el-dialog__body {
    padding: 16px 16px 8px;
  }

  .wild-help-overlay .help-content section {
    padding: 14px;
  }

  .wild-help-overlay .help-dialog .el-dialog__footer {
    padding: 12px 16px 16px;
  }
}
</style>
