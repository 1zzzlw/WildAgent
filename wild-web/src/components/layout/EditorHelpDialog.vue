<template>
  <Teleport to="body">
      <Transition name="wild-help-modal">
        <div
          v-if="visible"
          ref="helpOverlay"
          class="wild-help-modal__overlay"
          tabindex="-1"
          @click.self="closeHelp"
          @keydown.esc="closeHelp"
        >
          <section
            class="wild-help-modal__panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="wild-help-modal-title"
          >
            <header class="wild-help-modal__header">
              <div>
                <p class="wild-help-modal__eyebrow">WILD EDITOR</p>
                <h2 id="wild-help-modal-title">
                  {{ helpSection === 'guide' ? '项目介绍与快速上手' : '更新日志' }}
                </h2>
              </div>
              <button class="wild-help-modal__close" type="button" aria-label="关闭" @click="closeHelp">×</button>
            </header>

            <nav class="wild-help-modal__tabs" aria-label="帮助内容">
              <button
                type="button"
                :class="{ active: helpSection === 'guide' }"
                @click="helpSection = 'guide'"
              >
                项目介绍
              </button>
              <button
                type="button"
                :class="{ active: helpSection === 'changelog' }"
                @click="helpSection = 'changelog'"
              >
                更新日志
              </button>
            </nav>

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
          <h3>PBR 与程序化 Shader</h3>
          <ul>
            <li><strong>PBR 素材</strong>来自用户上传的图片，适合需要真实照片纹理、品牌材料或固定视觉效果的表面。</li>
            <li><strong>默认表面 Shader</strong>不依赖图片，已覆盖矿物/灰泥、砌体、木材、金属和中性表面；<code>brick</code> 是其中更精细的专用砖材实现。</li>
            <li>“新红砖、自然旧红砖、潮湿盐碱红砖”是同一 <code>brick</code> Shader 的语义配方，不是三个渲染类型。</li>
            <li>世界默认 Shader 始终提供克制的基础表面，可在右侧“素材”面板做 A/B 关闭；AI 聊天栏的 <strong>Shader</strong> 开关只控制 AI 是否主动生成专用程序化配方。</li>
            <li>启用后，配方会在安全参数范围内根据建筑语义生成可复现的小幅变化；明确指定颜色、灰缝或风化程度时，以用户要求为准。</li>
            <li>PBR 与 Shader 都通过统一材质角色绑定到墙体等构件；已有合适 PBR 时优先复用，否则可选择程序化效果。</li>
            <li><code>.wildmat</code> 从右侧“素材”面板导入，之后由用户应用到已选构件；<code>.wildlook</code> 从右侧“光影”面板导入，导入后需明确启用，切换时旧光影资源会释放。</li>
            <li>标准 ZIP/ZIP64 包会校验路径、解压体积、资源 SHA-256 和图片类型；支持 PNG/JPEG/WebP 与 KTX2。</li>
          </ul>
        </section>

        <section>
          <h3>全局环境与天气</h3>
          <ul>
            <li>环境天气属于整个世界，与草地、雪山、沙漠等场景环境同级，不写入任何单栋建筑 Blueprint。</li>
            <li>右侧“光影”面板提供晴天、多云、雨天、雾天、雪天和沙尘预设；预设会同时调整云量、雾、湿润、风及相关材质响应。</li>
            <li>高级参数可以继续微调降雨、积雪、积尘、云量、雾和风力；雨雪会显示全局动态效果，并同步改变天空、光照、曝光和能见度。</li>
            <li>顶部白天/黄昏/夜晚按钮控制太阳与月亮；云雾会自然降低天体可见度。</li>
          </ul>
        </section>

        <section>
          <h3>组件库与选择</h3>
          <ul>
            <li>完成世界材质与光影 Phase 6–10 基础链路：包导入管理、ZIP/ZIP64、KTX2、天气响应、世界文档、多蓝图实例和资源解析接口。</li>
            <li>默认世界光影重新调整太阳/环境光比例、曝光和阴影层次；画质档位现在会实时控制默认表面 Shader 强度。</li>
            <li>湿润、雨痕、积雪和积尘统一作用于默认程序化表面、专用砖和 PBR 材质，并可独立关闭。</li>
            <li>组件库可添加门、窗、阳台、雨棚、栏杆、灯具等组合组件；渲染前会统一展开为基础几何。</li>
            <li>未指定主入口尺寸时，系统会在合理通行范围内生成稳定变化；门扇带有基础门板和把手轮廓，并继续支持右键开合。</li>
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
            <li>新增世界级天气面板：晴天、多云、雨天、雾天、雪天和沙尘统一驱动天空、主光、曝光、雾、雨雪可视效果与材质环境响应。</li>
            <li>新增程序化太阳与月亮，并将天气从建筑 Blueprint 中移出；多蓝图实例共享同一世界环境状态。</li>
            <li>新增 AI 自动 Shader 开关并默认关闭；快速模式和精密模式均执行服务端兜底，未开启时不会下发程序化材质。</li>
            <li>新增普通阳台槽位推导：阳台与对应上层立面开口按中心轴对齐，避免模型自由坐标造成横向偏移。</li>
            <li>程序化红砖从固定参数预设升级为语义范围配方：不同建筑具有稳定的小幅差异，同一项目重复生成保持一致。</li>
            <li>修复密集立面轴网可能把主入口压缩为窄门的问题；默认主入口保持合理通行尺寸。</li>
            <li>增强通用门构件表现，增加门板层次和把手轮廓，同时保持门扇整体开合交互。</li>
            <li>新增组件材质语义默认值：门窗、凸窗、栏杆、阳台、雨棚等不再因材质缺失显示为统一白色。</li>
            <li>灯泡升级为透明玻璃外壳与独立发光内芯，并保留右键三档灯光互动。</li>
            <li>完善 PBR 素材入库与复用：支持单图导入、颜色调整、法线强度、真实尺寸和多个可选纹理通道。</li>
            <li>新增 Ctrl + 左键多选、空白处取消选择，以及选中组件批量处理能力。</li>
            <li>增强复杂建筑的通用校验与修复：按结构、坐标、宿主、覆盖、设计约束等类别处理，减少单建筑补丁和无效重试。</li>
            <li>修复工具调用返回列表时触发的 <code>list object has no attribute values</code> 容器兼容错误。</li>
            <li>改进高层住宅塔楼生成约束、标准层复用、核心筒、剪力墙与规则立面表达。</li>
            <li>实现首个无图片程序化材质类型 <code>brick</code>，支持砖尺寸、灰缝凹陷、色差、粗糙度、风化、盐碱、雨痕和墙脚潮湿参数。</li>
          </ul>
        </section>

        <section>
          <div class="release-title"><strong>稳定性原则</strong></div>
          <p>所有建筑问题优先映射到有限的通用类别，通过共享校验器、确定性修复、协议约束和参数化测试解决，不按建筑名称或组件 ID 堆叠永久补丁。</p>
        </section>
            </div>

            <footer class="wild-help-modal__footer">
              <button type="button" @click="closeHelp">知道了</button>
            </footer>
          </section>
        </div>
      </Transition>
    </Teleport>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ close: [] }>()
const helpSection = ref<'guide' | 'changelog'>('guide')
const helpOverlay = ref<HTMLElement | null>(null)

watch(() => props.visible, (visible) => {
  if (!visible) return
  helpSection.value = 'guide'
  nextTick(() => helpOverlay.value?.focus())
})

function closeHelp() {
  emit('close')
}
</script>

<style scoped>
.wild-help-modal__overlay {
  position: fixed;
  z-index: 3000;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(8, 11, 16, 0.72);
  backdrop-filter: blur(4px);
  outline: none;
}

.wild-help-modal__panel {
  display: flex;
  width: min(760px, calc(100vw - 48px));
  max-height: min(86vh, 820px);
  overflow: hidden;
  flex-direction: column;
  border: 1px solid #42464f;
  border-radius: 12px;
  background: #25272c;
  box-shadow: 0 24px 72px rgba(0, 0, 0, 0.55);
  color: #d8dbe2;
}

.wild-help-modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 22px 16px;
  border-bottom: 1px solid #393c43;
}

.wild-help-modal__eyebrow {
  margin: 0 0 3px;
  color: #55bfe6;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

.wild-help-modal__header h2 {
  margin: 0;
  color: #f5f6f8;
  font-size: 19px;
  font-weight: 600;
}

.wild-help-modal__close {
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #aeb3bd;
  cursor: pointer;
  font-size: 24px;
  line-height: 30px;
}

.wild-help-modal__close:hover {
  background: #373a41;
  color: #ffffff;
}

.wild-help-modal__tabs {
  display: flex;
  gap: 4px;
  padding: 10px 22px 0;
}

.wild-help-modal__tabs button {
  padding: 7px 12px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: #aeb3bd;
  cursor: pointer;
  font-size: 13px;
}

.wild-help-modal__tabs button:hover {
  color: #e8ebef;
}

.wild-help-modal__tabs button.active {
  border-bottom-color: #3aaed8;
  color: #ffffff;
}

.help-content {
  min-height: 0;
  overflow-y: auto;
  padding: 16px 22px 20px;
  color: #cdd1d8;
  font-size: 14px;
  line-height: 1.68;
  scrollbar-color: #555b66 transparent;
  scrollbar-width: thin;
}

.help-content section {
  padding: 14px 16px;
  border: 1px solid #393d45;
  border-radius: 8px;
  background: #2b2e34;
}

.help-content section + section {
  margin-top: 10px;
}

.help-content h3 {
  margin: 0 0 8px;
  color: #f0f2f5;
  font-size: 15px;
  font-weight: 600;
}

.help-content p,
.help-content ul,
.help-content ol {
  margin: 0;
}

.help-content ul,
.help-content ol {
  padding-left: 21px;
}

.help-content li + li {
  margin-top: 5px;
}

.help-content li::marker {
  color: #48b9df;
}

.help-content strong {
  color: #f2f4f7;
}

.help-lead {
  margin-bottom: 12px !important;
  padding: 12px 14px;
  border-left: 3px solid #3aaed8;
  border-radius: 5px;
  background: #29343c;
  color: #e2f2f8;
}

.help-tip {
  margin-top: 12px;
  padding: 11px 13px;
  border: 1px solid #34505c;
  border-radius: 7px;
  background: #29373e;
  color: #bce8f6;
}

.release-title {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 8px;
  color: #ffffff;
}

.release-title span {
  padding: 1px 8px;
  border-radius: 999px;
  background: #236a86;
  color: #d9f5ff;
  font-size: 11px;
}

.help-content kbd,
.help-content code {
  padding: 1px 5px;
  border: 1px solid #505660;
  border-radius: 4px;
  background: #1b1d21;
  color: #f0f2f4;
  font-family: Consolas, monospace;
}

.wild-help-modal__footer {
  display: flex;
  justify-content: flex-end;
  padding: 12px 22px 18px;
  border-top: 1px solid #393c43;
}

.wild-help-modal__footer button {
  min-width: 88px;
  padding: 8px 16px;
  border: 1px solid #168bc2;
  border-radius: 5px;
  background: #137fac;
  color: #ffffff;
  cursor: pointer;
}

.wild-help-modal__footer button:hover {
  border-color: #35bfe8;
  background: #1593c7;
}

.wild-help-modal-enter-active,
.wild-help-modal-leave-active {
  transition: opacity 0.16s ease;
}

.wild-help-modal-enter-active .wild-help-modal__panel,
.wild-help-modal-leave-active .wild-help-modal__panel {
  transition: transform 0.16s ease, opacity 0.16s ease;
}

.wild-help-modal-enter-from,
.wild-help-modal-leave-to {
  opacity: 0;
}

.wild-help-modal-enter-from .wild-help-modal__panel,
.wild-help-modal-leave-to .wild-help-modal__panel {
  opacity: 0;
  transform: translateY(8px) scale(0.985);
}

@media (max-width: 680px) {
  .wild-help-modal__overlay {
    padding: 12px;
  }

  .wild-help-modal__panel {
    width: calc(100vw - 24px);
    max-height: 92vh;
  }

  .wild-help-modal__header,
  .help-content,
  .wild-help-modal__footer {
    padding-right: 16px;
    padding-left: 16px;
  }

  .wild-help-modal__tabs {
    padding-left: 16px;
  }
}
</style>
