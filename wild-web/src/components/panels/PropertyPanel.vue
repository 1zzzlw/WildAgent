<template>
  <div class="property-panel">
    <div class="panel-header">
      <span>属性面板</span>
    </div>
    <div class="panel-body">
      <div v-if="!selectedItem" class="empty-state">
        未选中任何构件
      </div>
      <div v-else class="properties">
        <div class="property-section">
          <div class="section-title">基本信息</div>
          <div class="property-row">
            <label>ID</label>
            <el-input :model-value="selectedItem.id" readonly />
          </div>
          <div class="property-row">
            <label>类型</label>
            <el-input :model-value="selectedItem.type" readonly />
          </div>
          <div v-if="selectedComponent" class="component-badge">组合构件 · 编译后整体编辑</div>
        </div>

        <template v-if="selectedComponent">
          <div class="property-section behavior-card">
            <div class="section-title">视口编辑</div>
            <div class="property-row behavior-row">
              <div>
                <label>允许拖动</label>
                <div class="behavior-description">开启后显示三轴移动控件</div>
              </div>
              <el-switch :model-value="selectedComponent.draggable || false" inline-prompt
                active-text="开" inactive-text="关" @change="handleDraggableEnabled" />
            </div>
            <div class="interaction-hint">拖动只更新组件坐标；自动吸附、对齐和碰撞校验留到后续阶段。</div>
          </div>

          <div v-if="hasWallAttachment" class="property-section">
            <div class="section-title">墙体依附</div>
            <div v-if="hasOpeningHeight" class="property-row">
              <label>父墙</label>
              <el-select :model-value="componentString('parentWall')"
                @change="(value: string) => handleComponentChange('parentWall', value)">
                <el-option v-for="wall in walls" :key="wall.id" :label="wall.id" :value="wall.id" />
              </el-select>
            </div>
            <div class="property-row vector-property">
              <label>位置</label>
              <div class="vector-inputs">
                <div v-for="(axis, index) in axes" :key="axis" class="axis-input">
                  <span class="axis-label">{{ axis }}</span>
                  <el-input-number :model-value="componentVectorValue('from', index)" :step="0.1"
                    :controls="false" :aria-label="`位置 ${axis}`"
                    @change="(value: number | undefined) => handleComponentVectorChange('from', index, value)" />
                </div>
              </div>
            </div>
            <div class="property-row">
              <label>宽度</label>
              <el-input-number :model-value="componentNumber('width')" :min="0.01" :step="0.1"
                @change="(value: number | undefined) => handleComponentNumberChange('width', value)" />
            </div>
            <div class="property-row">
              <label>高度</label>
              <el-input-number :model-value="componentNumber('height')" :min="0.01" :step="0.1"
                @change="(value: number | undefined) => handleComponentNumberChange('height', value)" />
            </div>
          </div>

          <div v-if="hasFrame" class="property-section">
            <div class="section-title">边框</div>
            <div class="property-row">
              <label>边框宽度</label>
              <el-input-number :model-value="componentOptionalNumber('frameWidth')" :min="0.01" :step="0.01"
                @change="(value: number | undefined) => handleComponentNumberChange('frameWidth', value)" />
            </div>
            <div class="property-row">
              <label>边框深度</label>
              <el-input-number :model-value="componentOptionalNumber('frameDepth')" :min="0.01" :step="0.01"
                @change="(value: number | undefined) => handleComponentNumberChange('frameDepth', value)" />
            </div>
            <div class="property-row">
              <label>边框材质</label>
              <el-select :model-value="componentString('frameMaterial')" placeholder="未指定"
                @change="(value: string) => handleComponentChange('frameMaterial', value)">
                <el-option v-for="name in materialNames" :key="name" :label="name" :value="name" />
              </el-select>
            </div>
          </div>

          <div v-if="selectedComponent.type === 'door'" class="property-section">
            <div class="section-title">门</div>
            <div class="property-row">
              <label>门扇厚度</label>
              <el-input-number :model-value="componentOptionalNumber('leafDepth')" :min="0.005" :step="0.005"
                @change="(value: number | undefined) => handleComponentNumberChange('leafDepth', value)" />
            </div>
            <div class="property-row">
              <label>门扇材质</label>
              <el-select :model-value="componentString('leafMaterial')" placeholder="未指定"
                @change="(value: string) => handleComponentChange('leafMaterial', value)">
                <el-option v-for="name in materialNames" :key="name" :label="name" :value="name" />
              </el-select>
            </div>
          </div>

          <div v-if="selectedComponent.type === 'window'" class="property-section">
            <div class="section-title">窗</div>
            <div class="property-row">
              <label>玻璃厚度</label>
              <el-input-number :model-value="componentOptionalNumber('glassDepth')" :min="0.002" :step="0.002"
                @change="(value: number | undefined) => handleComponentNumberChange('glassDepth', value)" />
            </div>
            <div class="property-row">
              <label>竖窗棂</label>
              <el-input-number :model-value="componentNumber('verticalMullions', 0)" :min="0" :max="32" :step="1"
                @change="(value: number | undefined) => handleComponentIntegerChange('verticalMullions', value)" />
            </div>
            <div class="property-row">
              <label>横窗棂</label>
              <el-input-number :model-value="componentNumber('horizontalMullions', 0)" :min="0" :max="32" :step="1"
                @change="(value: number | undefined) => handleComponentIntegerChange('horizontalMullions', value)" />
            </div>
            <div class="property-row">
              <label>玻璃材质</label>
              <el-select :model-value="componentString('glassMaterial')" placeholder="未指定"
                @change="(value: string) => handleComponentChange('glassMaterial', value)">
                <el-option v-for="name in materialNames" :key="name" :label="name" :value="name" />
              </el-select>
            </div>
          </div>

          <div v-if="selectedComponent.type === 'door' || selectedComponent.type === 'window'"
            class="property-section behavior-card">
            <div class="section-title">右键开合</div>
            <div class="property-row behavior-row">
              <div>
                <label>启用交互</label>
                <div class="behavior-description">右键门扇或窗扇执行动画</div>
              </div>
              <el-switch :model-value="!!componentInteraction" inline-prompt
                active-text="开" inactive-text="关" @change="handleInteractionEnabled" />
            </div>
            <template v-if="componentInteraction">
              <div class="property-row">
                <label>开合方式</label>
                <el-select :model-value="componentInteraction.mode"
                  @change="(value: string) => handleInteractionChange('mode', value)">
                  <el-option label="旋转平开" value="swing" />
                  <el-option label="水平推拉" value="slide" />
                </el-select>
              </div>
              <div v-if="selectedComponent.type === 'door'" class="property-row">
                <label>开启方向</label>
                <el-select :model-value="componentInteraction.hingeSide || 'left'"
                  @change="(value: string) => handleInteractionChange('hingeSide', value)">
                  <el-option label="左侧" value="left" />
                  <el-option label="右侧" value="right" />
                </el-select>
              </div>
              <div v-if="componentInteraction.mode === 'swing'" class="property-row">
                <label>最大角度</label>
                <el-input-number :model-value="componentInteraction.openAngle || 90" :min="1" :max="180" :step="5"
                  @change="(value: number | undefined) => handleInteractionNumberChange('openAngle', value)" />
              </div>
              <div v-else class="property-row">
                <label>推拉距离</label>
                <el-input-number :model-value="componentInteraction.openDistance" :min="0.01" :step="0.1"
                  placeholder="自动"
                  @change="(value: number | undefined) => handleInteractionNumberChange('openDistance', value)" />
              </div>
              <div class="property-row">
                <label>初始开启</label>
                <el-switch :model-value="componentInteraction.initiallyOpen || false" inline-prompt
                  active-text="开" inactive-text="关"
                  @change="(value: boolean) => handleInteractionChange('initiallyOpen', value)" />
              </div>
              <div class="interaction-hint">{{ selectedComponent.type === 'window'
                ? '右键命中左窗扇就开左侧，命中右窗扇就开右侧；两扇可分别打开。'
                : '视口中左键选择，右键命中门扇执行开合。' }}</div>
            </template>
          </div>

          <div v-if="selectedComponent.type === 'light'" class="property-section behavior-card">
            <div class="section-title">灯光参数</div>
            <div class="property-row vector-property">
              <label>位置</label>
              <div class="vector-inputs">
                <div v-for="(axis, axisIndex) in axes" :key="axis" class="axis-input">
                  <span class="axis-label">{{ axis }}</span>
                  <el-input-number :model-value="componentVectorValue('position', axisIndex)" :controls="false" :step="0.1"
                    @change="(value: number | undefined) => handleComponentVectorChange('position', axisIndex, value)" />
                </div>
              </div>
            </div>
            <div class="property-row">
              <label>灯具类型</label>
              <el-select :model-value="componentString('fixtureType') || 'bulb'"
                @change="(value: string) => handleComponentChange('fixtureType', value)">
                <el-option label="裸灯泡" value="bulb" />
                <el-option label="台灯" value="table_lamp" />
              </el-select>
            </div>
            <div class="property-row">
              <label>光源类型</label>
              <el-select :model-value="componentString('lightType') || 'point'"
                @change="(value: string) => handleComponentChange('lightType', value)">
                <el-option label="点光源" value="point" />
                <el-option label="聚光灯" value="spot" />
              </el-select>
            </div>
            <div class="property-row">
              <label>灯光颜色</label>
              <el-color-picker :model-value="lightColorHex" color-format="hex"
                @change="handleLightColorChange" />
            </div>
            <div v-for="field in lightNumberFields" :key="field.key" class="property-row">
              <label>{{ field.label }}</label>
              <el-input-number :model-value="componentOptionalNumber(field.key, field.defaultValue)"
                :min="field.min" :max="field.max" :step="field.step"
                @change="(value: number | undefined) => handleComponentNumberChange(field.key, value)" />
            </div>
            <div class="property-row behavior-row">
              <label>初始亮灯</label>
              <el-switch :model-value="componentValue('initiallyOn') === true" inline-prompt
                active-text="开" inactive-text="关"
                @change="(value: boolean) => handleComponentChange('initiallyOn', value)" />
            </div>
            <div class="interaction-hint">右键灯泡循环切换：关闭 → 弱光 → 强光 → 关闭。</div>
          </div>

          <div v-if="selectedComponent.type === 'canopy'" class="property-section">
            <div class="section-title">雨棚参数</div>
            <div v-for="field in canopyNumberFields" :key="field.key" class="property-row">
              <label>{{ field.label }}</label>
              <el-input-number :model-value="componentOptionalNumber(field.key, field.defaultValue)"
                :min="field.min" :step="field.step"
                @change="(value: number | undefined) => field.integer
                  ? handleComponentIntegerChange(field.key, value)
                  : handleComponentNumberChange(field.key, value)" />
            </div>
            <div v-for="materialField in [{ key: 'material', label: '顶板材质' }, { key: 'supportMaterial', label: '支柱材质' }]"
              :key="materialField.key" class="property-row">
              <label>{{ materialField.label }}</label>
              <el-select :model-value="componentString(materialField.key)" placeholder="未指定"
                @change="(value: string) => handleComponentChange(materialField.key, value)">
                <el-option v-for="name in materialNames" :key="name" :label="name" :value="name" />
              </el-select>
            </div>
          </div>

          <div v-if="selectedComponent.type === 'balcony'" class="property-section">
            <div class="section-title">阳台参数</div>
            <div v-for="field in balconyNumberFields" :key="field.key" class="property-row">
              <label>{{ field.label }}</label>
              <el-input-number :model-value="componentOptionalNumber(field.key, field.defaultValue)"
                :min="0.01" :step="field.step"
                @change="(value: number | undefined) => handleComponentNumberChange(field.key, value)" />
            </div>
            <div class="property-row">
              <label>楼板材质</label>
              <el-select :model-value="componentString('material')" placeholder="未指定"
                @change="(value: string) => handleComponentChange('material', value)">
                <el-option v-for="name in materialNames" :key="name" :label="name" :value="name" />
              </el-select>
            </div>
            <div class="property-row">
              <label>栏杆材质</label>
              <el-select :model-value="componentString('railingMaterial')" placeholder="未指定"
                @change="(value: string) => handleComponentChange('railingMaterial', value)">
                <el-option v-for="name in materialNames" :key="name" :label="name" :value="name" />
              </el-select>
            </div>
          </div>

          <div v-if="selectedComponent.type === 'bay_window'" class="property-section">
            <div class="section-title">凸窗参数</div>
            <div class="property-row">
              <label>凸出深度</label>
              <el-input-number :model-value="componentNumber('projectionDepth')" :min="0.01" :step="0.1"
                @change="(value: number | undefined) => handleComponentNumberChange('projectionDepth', value)" />
            </div>
            <div class="property-row">
              <label>玻璃材质</label>
              <el-select :model-value="componentString('glassMaterial')" placeholder="未指定"
                @change="(value: string) => handleComponentChange('glassMaterial', value)">
                <el-option v-for="name in materialNames" :key="name" :label="name" :value="name" />
              </el-select>
            </div>
          </div>

          <div v-if="selectedComponent.type === 'ramp'" class="property-section">
            <div class="section-title">坡道参数</div>
            <div class="property-row">
              <label>父楼板</label>
              <el-select :model-value="componentString('parentFloor')" placeholder="世界坐标" clearable
                @clear="clearComponentField('parentFloor')"
                @change="(value: string) => handleComponentChange('parentFloor', value)">
                <el-option v-for="floor in floors" :key="floor.id" :label="floor.id" :value="floor.id" />
              </el-select>
            </div>
            <div v-for="vectorField in [{ key: 'from', label: '起点' }, { key: 'to', label: '终点' }]"
              :key="vectorField.key" class="property-row vector-property">
              <label>{{ vectorField.label }}</label>
              <div class="vector-inputs">
                <div v-for="(axis, axisIndex) in axes" :key="axis" class="axis-input">
                  <span class="axis-label">{{ axis }}</span>
                  <el-input-number :model-value="componentVectorValue(vectorField.key, axisIndex)" :controls="false" :step="0.1"
                    @change="(value: number | undefined) => handleComponentVectorChange(vectorField.key, axisIndex, value)" />
                </div>
              </div>
            </div>
            <div v-for="field in rampNumberFields" :key="field.key" class="property-row">
              <label>{{ field.label }}</label>
              <el-input-number :model-value="componentOptionalNumber(field.key, field.defaultValue)"
                :min="0.01" :step="field.step"
                @change="(value: number | undefined) => handleComponentNumberChange(field.key, value)" />
            </div>
            <div class="property-row">
              <label>栏杆侧</label>
              <el-select :model-value="componentString('railingSides') || 'both'"
                @change="(value: string) => handleComponentChange('railingSides', value)">
                <el-option label="无" value="none" />
                <el-option label="左侧" value="left" />
                <el-option label="右侧" value="right" />
                <el-option label="双侧" value="both" />
              </el-select>
            </div>
            <div v-for="materialField in [{ key: 'material', label: '坡道材质' }, { key: 'railingMaterial', label: '栏杆材质' }]"
              :key="materialField.key" class="property-row">
              <label>{{ materialField.label }}</label>
              <el-select :model-value="componentString(materialField.key)" placeholder="未指定"
                @change="(value: string) => handleComponentChange(materialField.key, value)">
                <el-option v-for="name in materialNames" :key="name" :label="name" :value="name" />
              </el-select>
            </div>
          </div>

          <div v-if="selectedComponent.type === 'cornice'" class="property-section">
            <div class="property-row">
              <label>父屋顶</label>
              <el-select :model-value="componentString('parentRoof')" placeholder="世界坐标" clearable
                @clear="clearComponentField('parentRoof')"
                @change="(value: string) => handleComponentChange('parentRoof', value)">
                <el-option v-for="roof in roofs" :key="roof.id" :label="roof.id" :value="roof.id" />
              </el-select>
            </div>
            <div class="property-row">
              <label>材质</label>
              <el-select :model-value="componentString('material')" placeholder="未指定"
                @change="(value: string) => handleComponentChange('material', value)">
                <el-option v-for="name in materialNames" :key="name" :label="name" :value="name" />
              </el-select>
            </div>
            <div class="section-title section-title-row">
              <span>檐口路径</span>
              <el-button size="small" @click="addPathPoint">添加点</el-button>
            </div>
            <div v-for="(point, pointIndex) in pathPoints" :key="pointIndex" class="array-item">
              <div class="array-item-title">
                <span>点 {{ pointIndex + 1 }}</span>
                <el-button v-if="pathPoints.length > 2" link type="danger" @click="removePathPoint(pointIndex)">删除</el-button>
              </div>
              <div class="vector-inputs">
                <div v-for="(axis, axisIndex) in axes" :key="axis" class="axis-input">
                  <span class="axis-label">{{ axis }}</span>
                  <el-input-number :model-value="point[axisIndex]" :step="0.1" :controls="false"
                    @change="(value: number | undefined) => handlePathPointChange(pointIndex, axisIndex, value)" />
                </div>
              </div>
            </div>
            <div class="section-title section-title-row subsection-title">
              <span>二维截面</span>
              <el-button size="small" @click="addProfilePoint">添加点</el-button>
            </div>
            <div v-for="(point, index) in profilePoints" :key="index" class="profile-row">
              <el-input-number :model-value="point[0]" :controls="false" :step="0.01"
                @change="(value: number | undefined) => handleProfilePointChange(index, 0, value)" />
              <el-input-number :model-value="point[1]" :controls="false" :step="0.01"
                @change="(value: number | undefined) => handleProfilePointChange(index, 1, value)" />
              <el-button v-if="profilePoints.length > 3" link type="danger" @click="removeProfilePoint(index)">删除</el-button>
            </div>
          </div>

          <div v-if="selectedComponent.type === 'chimney'" class="property-section">
            <div class="section-title">烟囱参数</div>
            <div class="property-row">
              <label>父屋顶</label>
              <el-select :model-value="componentString('parentRoof')" placeholder="世界坐标" clearable
                @clear="clearComponentField('parentRoof')"
                @change="(value: string) => handleComponentChange('parentRoof', value)">
                <el-option v-for="roof in roofs" :key="roof.id" :label="roof.id" :value="roof.id" />
              </el-select>
            </div>
            <div class="property-row vector-property">
              <label>位置</label>
              <div class="vector-inputs">
                <div v-for="(axis, axisIndex) in axes" :key="axis" class="axis-input">
                  <span class="axis-label">{{ axis }}</span>
                  <el-input-number :model-value="componentVectorValue('position', axisIndex)" :controls="false" :step="0.1"
                    @change="(value: number | undefined) => handleComponentVectorChange('position', axisIndex, value)" />
                </div>
              </div>
            </div>
            <div v-for="field in chimneyNumberFields" :key="field.key" class="property-row">
              <label>{{ field.label }}</label>
              <el-input-number :model-value="componentOptionalNumber(field.key, field.defaultValue)"
                :min="0.01" :step="field.step"
                @change="(value: number | undefined) => handleComponentNumberChange(field.key, value)" />
            </div>
            <div v-for="materialField in [{ key: 'material', label: '筒体材质' }, { key: 'capMaterial', label: '压顶材质' }]"
              :key="materialField.key" class="property-row">
              <label>{{ materialField.label }}</label>
              <el-select :model-value="componentString(materialField.key)" placeholder="未指定"
                @change="(value: string) => handleComponentChange(materialField.key, value)">
                <el-option v-for="name in materialNames" :key="name" :label="name" :value="name" />
              </el-select>
            </div>
          </div>

          <div v-if="selectedComponent.type === 'railing'" class="property-section">
            <div class="section-title">栏杆参数</div>
            <div class="property-row">
              <label>父楼板</label>
              <el-select :model-value="componentString('parentFloor')" placeholder="世界坐标" clearable
                @clear="clearComponentField('parentFloor')"
                @change="(value: string) => handleComponentChange('parentFloor', value)">
                <el-option v-for="floor in floors" :key="floor.id" :label="floor.id" :value="floor.id" />
              </el-select>
            </div>
            <div v-for="field in railingNumberFields" :key="field.key" class="property-row">
              <label>{{ field.label }}</label>
              <el-input-number :model-value="componentOptionalNumber(field.key, field.defaultValue)"
                :min="0.001" :step="field.step"
                @change="(value: number | undefined) => handleComponentNumberChange(field.key, value)" />
            </div>
            <div class="property-row">
              <label>材质</label>
              <el-select :model-value="componentString('material')" placeholder="未指定"
                @change="(value: string) => handleComponentChange('material', value)">
                <el-option v-for="name in materialNames" :key="name" :label="name" :value="name" />
              </el-select>
            </div>
          </div>

          <div v-if="selectedComponent.type === 'railing'" class="property-section">
            <div class="section-title section-title-row">
              <span>路径点</span>
              <el-button size="small" @click="addPathPoint">添加点</el-button>
            </div>
            <div v-for="(point, pointIndex) in selectedComponent.path" :key="pointIndex" class="array-item">
              <div class="array-item-title">
                <span>点 {{ pointIndex + 1 }}</span>
                <el-button v-if="selectedComponent.path.length > 2" link type="danger"
                  @click="removePathPoint(pointIndex)">删除</el-button>
              </div>
              <div class="vector-inputs">
                <div v-for="(axis, axisIndex) in axes" :key="axis" class="axis-input">
                  <span class="axis-label">{{ axis }}</span>
                  <el-input-number :model-value="point[axisIndex]" :step="0.1" :controls="false"
                    :aria-label="`路径点 ${pointIndex + 1} ${axis}`"
                    @change="(value: number | undefined) => handlePathPointChange(pointIndex, axisIndex, value)" />
                </div>
              </div>
            </div>
          </div>

          <div v-if="selectedComponent.type === 'railing'" class="property-section">
            <div class="section-title section-title-row">
              <span>横杆高度比例</span>
              <el-button size="small" :disabled="railLevels.length >= 8" @click="addRailLevel">添加</el-button>
            </div>
            <div v-for="(level, index) in railLevels" :key="index" class="array-number-row">
              <el-input-number :model-value="level" :min="0.01" :max="1" :step="0.1"
                @change="(value: number | undefined) => handleRailLevelChange(index, value)" />
              <el-button v-if="railLevels.length > 1" link type="danger" @click="removeRailLevel(index)">删除</el-button>
            </div>
          </div>

          <div class="danger-zone">
            <el-button type="danger" plain @click="removeSelectedComponent">删除组合构件</el-button>
          </div>
        </template>

        <div class="property-section" v-if="selectedElement?.type === 'column'">
          <div class="section-title">柱子参数</div>
          <div class="property-row">
            <label>高度</label>
            <el-input-number :model-value="(selectedElement as any).height" :step="0.1"
              @update:model-value="(value: string | number | null | undefined) => handleChange('height', value)" />
          </div>
          <div class="property-row">
            <label>底部半径</label>
            <el-input-number :model-value="(selectedElement as any).bottomRadius" :step="0.1"
              @update:model-value="(value: string | number | null | undefined) => handleChange('bottomRadius', value)" />
          </div>
          <div class="property-row">
            <label>顶部半径</label>
            <el-input-number :model-value="(selectedElement as any).topRadius" :step="0.1"
              @update:model-value="(value: string | number | null | undefined) => handleChange('topRadius', value)" />
          </div>
        </div>

        <div class="property-section" v-if="selectedElement?.type === 'wall'">
          <div class="section-title">墙体参数</div>
          <div class="property-row">
            <label>高度</label>
            <el-input-number :model-value="(selectedElement as any).height" :step="0.1"
              @update:model-value="(value: string | number | null | undefined) => handleChange('height', value)" />
          </div>
          <div class="property-row">
            <label>厚度</label>
            <el-input-number :model-value="(selectedElement as any).thickness" :step="0.01"
              @update:model-value="(value: string | number | null | undefined) => handleChange('thickness', value)" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSceneStore } from '../../stores/sceneStore'
import { useSelectionStore } from '../../stores/selectionStore'
import { createPatch } from '../../wild/scenePatch'

const sceneStore = useSceneStore()
const selectionStore = useSelectionStore()
const axes = ['X', 'Y', 'Z'] as const
const railingNumberFields = [
  { key: 'height', label: '高度', step: 0.1, defaultValue: 1.1 },
  { key: 'postSpacing', label: '立杆间距', step: 0.1, defaultValue: 1.2 },
  { key: 'postRadius', label: '立杆半径', step: 0.005, defaultValue: 0.035 },
  { key: 'railRadius', label: '横杆半径', step: 0.005, defaultValue: 0.045 },
] as const
const canopyNumberFields = [
  { key: 'depth', label: '出挑深度', step: 0.1, defaultValue: 1.1, min: 0.01, integer: false },
  { key: 'thickness', label: '顶板厚度', step: 0.01, defaultValue: 0.12, min: 0.01, integer: false },
  { key: 'supportCount', label: '支柱数量', step: 1, defaultValue: 0, min: 0, integer: true },
  { key: 'supportSize', label: '支柱尺寸', step: 0.01, defaultValue: 0.06, min: 0.01, integer: false },
] as const
const balconyNumberFields = [
  { key: 'depth', label: '出挑深度', step: 0.1, defaultValue: 1.2 },
  { key: 'slabThickness', label: '楼板厚度', step: 0.01, defaultValue: 0.18 },
  { key: 'railingHeight', label: '栏杆高度', step: 0.1, defaultValue: 1.1 },
  { key: 'postSpacing', label: '立杆间距', step: 0.1, defaultValue: 0.9 },
] as const
const rampNumberFields = [
  { key: 'width', label: '宽度', step: 0.1, defaultValue: 1.2 },
  { key: 'thickness', label: '厚度', step: 0.01, defaultValue: 0.18 },
  { key: 'railingHeight', label: '栏杆高度', step: 0.1, defaultValue: 1.1 },
  { key: 'postSpacing', label: '立杆间距', step: 0.1, defaultValue: 0.9 },
] as const
const chimneyNumberFields = [
  { key: 'width', label: '宽度', step: 0.1, defaultValue: 0.7 },
  { key: 'depth', label: '深度', step: 0.1, defaultValue: 0.7 },
  { key: 'height', label: '高度', step: 0.1, defaultValue: 2 },
  { key: 'wallThickness', label: '壁厚', step: 0.01, defaultValue: 0.1 },
  { key: 'capHeight', label: '压顶高度', step: 0.01, defaultValue: 0.08 },
] as const
const lightNumberFields = computed(() => {
  const common = [
    { key: 'lowIntensity', label: '弱光强度', step: 5, defaultValue: 25, min: 0.1, max: undefined },
    { key: 'highIntensity', label: '强光强度', step: 5, defaultValue: 90, min: 0.1, max: undefined },
    { key: 'distance', label: '照射距离', step: 0.5, defaultValue: 12, min: 0.1, max: undefined },
    { key: 'angle', label: '聚光角度', step: 5, defaultValue: 45, min: 1, max: 90 },
  ]
  return componentString('fixtureType') === 'table_lamp'
    ? [
        ...common,
        { key: 'height', label: '台灯高度', step: 0.05, defaultValue: 0.72, min: 0.1, max: undefined },
        { key: 'shadeRadius', label: '灯罩半径', step: 0.01, defaultValue: 0.28, min: 0.05, max: undefined },
        { key: 'baseHeight', label: '底座厚度', step: 0.01, defaultValue: 0.07, min: 0.01, max: undefined },
      ]
    : [
        ...common,
        { key: 'bulbRadius', label: '灯泡半径', step: 0.01, defaultValue: 0.16, min: 0.01, max: undefined },
        { key: 'baseHeight', label: '灯座高度', step: 0.01, defaultValue: 0.12, min: 0.01, max: undefined },
      ]
})

const selectedComponent = computed(() => {
  const id = selectionStore.selectedIds[0]
  if (!id || !sceneStore.document) return null
  return sceneStore.document.blueprint.geometry.components?.find(component => component.id === id) || null
})

const selectedElement = computed(() => {
  const id = selectionStore.selectedIds[0]
  if (!id || !sceneStore.document) return null
  return sceneStore.document.blueprint.geometry.elements.find(e => e.id === id) || null
})

const selectedItem = computed(() => selectedComponent.value || selectedElement.value)
const hasWallAttachment = computed(() => (
  selectedComponent.value?.type === 'door'
  || selectedComponent.value?.type === 'window'
  || selectedComponent.value?.type === 'canopy'
  || selectedComponent.value?.type === 'balcony'
  || selectedComponent.value?.type === 'bay_window'
))
const hasOpeningHeight = computed(() => (
  selectedComponent.value?.type === 'door'
  || selectedComponent.value?.type === 'window'
  || selectedComponent.value?.type === 'bay_window'
))
const hasFrame = computed(() => hasOpeningHeight.value)
const walls = computed(() => (
  sceneStore.document?.blueprint.geometry.elements.filter(element => element.type === 'wall') || []
))
const floors = computed(() => (
  sceneStore.document?.blueprint.geometry.elements.filter(element => element.type === 'floor') || []
))
const roofs = computed(() => (
  sceneStore.document?.blueprint.geometry.elements.filter(element => element.type === 'roof') || []
))
const materialNames = computed(() => Object.keys(sceneStore.document?.blueprint.materials || {}))
const railLevels = computed(() => (
  selectedComponent.value?.type === 'railing'
    ? selectedComponent.value.railLevels || [1]
    : []
))
const componentInteraction = computed(() => {
  if (selectedComponent.value?.type === 'door' || selectedComponent.value?.type === 'window') {
    return selectedComponent.value.interaction || null
  }
  return null
})
const lightColorHex = computed(() => {
  if (selectedComponent.value?.type !== 'light') return '#ffd194'
  const raw = selectedComponent.value.color
  // 容错：color 可能是未经规范化的 hex 字符串
  if (typeof raw === 'string' && /^#[0-9a-f]{6}$/i.test(raw)) return raw
  const color = Array.isArray(raw) && raw.length === 3 ? raw : [1, 0.82, 0.58]
  return `#${color.map((channel: number) => Math.round(channel * 255).toString(16).padStart(2, '0')).join('')}`
})
const pathPoints = computed(() => {
  if (selectedComponent.value?.type === 'railing' || selectedComponent.value?.type === 'cornice') {
    return selectedComponent.value.path
  }
  return []
})
const profilePoints = computed(() => (
  selectedComponent.value?.type === 'cornice' ? selectedComponent.value.profile : []
))

function handleChange(key: string, value: string | number | null | undefined) {
  const numericValue = typeof value === 'number' ? value : parseFloat(String(value ?? ''))

  if (!Number.isFinite(numericValue) || !selectedElement.value || !sceneStore.document) return

  const patch = createPatch(
    sceneStore.document.revision,
    [{
      op: 'update_element',
      id: selectedElement.value.id,
      changes: { [key]: numericValue }
    }],
    'user'
  )

  sceneStore.applyPatch(patch)
}

function componentValue(key: string): unknown {
  return selectedComponent.value
    ? (selectedComponent.value as unknown as Record<string, unknown>)[key]
    : undefined
}

function componentString(key: string): string | undefined {
  const value = componentValue(key)
  return typeof value === 'string' ? value : undefined
}

function componentNumber(key: string, fallback = 0): number {
  const value = componentValue(key)
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function componentOptionalNumber(key: string, fallback?: number): number | undefined {
  const value = componentValue(key)
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function componentVectorValue(key: string, index: number): number {
  const value = componentValue(key)
  return Array.isArray(value) && typeof value[index] === 'number' ? value[index] : 0
}

async function applyComponentChanges(changes: Record<string, unknown>, summary: string) {
  if (!selectedComponent.value || !sceneStore.document) return
  const patch = createPatch(
    sceneStore.document.revision,
    [{ op: 'update_component', id: selectedComponent.value.id, changes }],
    'user',
    false,
    summary,
  )
  if (!await sceneStore.applyPatch(patch)) ElMessage.error('参数不符合组件约束，修改未应用')
}

function handleComponentChange(key: string, value: unknown) {
  if (value === undefined || value === null || value === '') return
  void applyComponentChanges({ [key]: value }, `修改${selectedComponent.value?.id}.${key}`)
}

function clearComponentField(key: string) {
  void applyComponentChanges({ [key]: undefined }, `清除${selectedComponent.value?.id}.${key}`)
}

function handleComponentNumberChange(key: string, value: number | undefined) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return
  void applyComponentChanges({ [key]: value }, `修改${selectedComponent.value?.id}.${key}`)
}

function handleComponentIntegerChange(key: string, value: number | undefined) {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) return
  void applyComponentChanges({ [key]: value }, `修改${selectedComponent.value?.id}.${key}`)
}

function handleComponentVectorChange(key: string, index: number, value: number | undefined) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return
  const current = componentValue(key)
  if (!Array.isArray(current) || current.length !== 3) return
  const next = [...current] as number[]
  next[index] = value
  void applyComponentChanges({ [key]: next }, `修改${selectedComponent.value?.id}.${key}`)
}

function handleInteractionEnabled(enabled: boolean) {
  void applyComponentChanges(
    { interaction: enabled ? { mode: 'swing', hingeSide: 'left', openAngle: 90 } : undefined },
    `${enabled ? '启用' : '关闭'}${selectedComponent.value?.id}右键开合`,
  )
}

function handleDraggableEnabled(enabled: boolean) {
  void applyComponentChanges(
    { draggable: enabled },
    `${enabled ? '启用' : '关闭'}${selectedComponent.value?.id}拖动`,
  )
}

function handleLightColorChange(value: string | null) {
  if (!value || !/^#[0-9a-f]{6}$/i.test(value)) return
  const color = [
    Number.parseInt(value.slice(1, 3), 16) / 255,
    Number.parseInt(value.slice(3, 5), 16) / 255,
    Number.parseInt(value.slice(5, 7), 16) / 255,
  ]
  void applyComponentChanges({ color }, `修改${selectedComponent.value?.id}灯光颜色`)
}

function handleInteractionChange(key: string, value: unknown) {
  if (!componentInteraction.value) return
  void applyComponentChanges(
    { interaction: { ...componentInteraction.value, [key]: value } },
    `修改${selectedComponent.value?.id}交互参数`,
  )
}

function handleInteractionNumberChange(key: string, value: number | undefined) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return
  handleInteractionChange(key, value)
}

function handlePathPointChange(pointIndex: number, axisIndex: number, value: number | undefined) {
  if (
    (selectedComponent.value?.type !== 'railing' && selectedComponent.value?.type !== 'cornice')
    || typeof value !== 'number'
    || !Number.isFinite(value)
  ) return
  const path = selectedComponent.value.path.map(point => [...point])
  path[pointIndex][axisIndex] = value
  void applyComponentChanges({ path }, `修改${selectedComponent.value.id}路径`)
}

function addPathPoint() {
  if (selectedComponent.value?.type !== 'railing' && selectedComponent.value?.type !== 'cornice') return
  const path = selectedComponent.value.path.map(point => [...point])
  const last = path[path.length - 1]
  path.push([last[0] + 1, last[1], last[2]])
  void applyComponentChanges({ path }, `添加${selectedComponent.value.id}路径点`)
}

function removePathPoint(index: number) {
  if (
    (selectedComponent.value?.type !== 'railing' && selectedComponent.value?.type !== 'cornice')
    || selectedComponent.value.path.length <= 2
  ) return
  const path = selectedComponent.value.path.filter((_, pointIndex) => pointIndex !== index)
  void applyComponentChanges({ path }, `删除${selectedComponent.value.id}路径点`)
}

function handleProfilePointChange(index: number, axis: number, value: number | undefined) {
  if (selectedComponent.value?.type !== 'cornice' || typeof value !== 'number' || !Number.isFinite(value)) return
  const profile = selectedComponent.value.profile.map(point => [...point] as [number, number])
  profile[index][axis] = value
  void applyComponentChanges({ profile }, `修改${selectedComponent.value.id}截面`)
}

function addProfilePoint() {
  if (selectedComponent.value?.type !== 'cornice') return
  const profile = selectedComponent.value.profile.map(point => [...point] as [number, number])
  const last = profile[profile.length - 1]
  profile.push([last[0] + 0.05, last[1]])
  void applyComponentChanges({ profile }, `添加${selectedComponent.value.id}截面点`)
}

function removeProfilePoint(index: number) {
  if (selectedComponent.value?.type !== 'cornice' || selectedComponent.value.profile.length <= 3) return
  void applyComponentChanges(
    { profile: selectedComponent.value.profile.filter((_, pointIndex) => pointIndex !== index) },
    `删除${selectedComponent.value.id}截面点`,
  )
}

function handleRailLevelChange(index: number, value: number | undefined) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0 || value > 1) return
  const levels = [...railLevels.value]
  levels[index] = value
  void applyComponentChanges({ railLevels: levels }, `修改${selectedComponent.value?.id}横杆高度`)
}

function addRailLevel() {
  if (railLevels.value.length >= 8) return
  const next = [0.25, 0.5, 0.75, 1].find(level => !railLevels.value.includes(level))
  if (next === undefined) return
  const levels = [...railLevels.value, next].sort((left, right) => left - right)
  void applyComponentChanges({ railLevels: levels }, `添加${selectedComponent.value?.id}横杆`)
}

function removeRailLevel(index: number) {
  if (railLevels.value.length <= 1) return
  void applyComponentChanges(
    { railLevels: railLevels.value.filter((_, levelIndex) => levelIndex !== index) },
    `删除${selectedComponent.value?.id}横杆`,
  )
}

async function removeSelectedComponent() {
  if (!selectedComponent.value || !sceneStore.document) return
  try {
    await ElMessageBox.confirm(`确定删除组合构件 ${selectedComponent.value.id}？`, '删除组合构件', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  const patch = createPatch(
    sceneStore.document.revision,
    [{ op: 'remove_component', id: selectedComponent.value.id }],
    'user',
    false,
    `删除${selectedComponent.value.id}`,
  )
  if (await sceneStore.applyPatch(patch)) selectionStore.clearSelection()
}
</script>

<style scoped>
.property-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.panel-header {
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 500;
  border-bottom: 1px solid #3e3e42;
}

.panel-body {
  flex: 1;
  overflow-y: auto;
}

.empty-state {
  padding: 24px;
  text-align: center;
  color: #666666;
  font-size: 13px;
}

.properties {
  padding: 8px;
}

.property-section {
  margin-bottom: 16px;
}

.behavior-card {
  padding: 10px;
  border: 1px solid #343b43;
  border-radius: 6px;
  background: linear-gradient(145deg, rgba(38, 44, 51, 0.92), rgba(29, 31, 36, 0.92));
}

.behavior-row {
  justify-content: space-between;
}

.behavior-row > div:first-child {
  min-width: 0;
}

.behavior-description {
  margin-top: 2px;
  color: #75838b;
  font-size: 10px;
}

.behavior-card :deep(.el-switch) {
  flex: 0 0 auto;
  --el-switch-on-color: #22a8d6;
  --el-switch-off-color: #4a4e55;
}

.section-title {
  font-size: 12px;
  font-weight: 500;
  color: #888888;
  margin-bottom: 8px;
  text-transform: uppercase;
}

.section-title-row,
.array-item-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.component-badge {
  margin-top: 8px;
  padding: 6px 8px;
  border: 1px solid #326b80;
  border-radius: 4px;
  background: rgba(42, 118, 145, 0.18);
  color: #8bd9f5;
  font-size: 11px;
}

.property-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.property-row label {
  flex: 0 0 80px;
  font-size: 12px;
}

.property-row :deep(.el-input),
.property-row :deep(.el-input-number),
.property-row :deep(.el-select) {
  flex: 1;
}

.vector-property {
  display: block;
}

.vector-property > label {
  display: block;
  margin-bottom: 6px;
}

.vector-inputs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px;
  width: 100%;
}

.array-item,
.array-number-row {
  margin-bottom: 8px;
}

.array-item {
  padding: 9px;
  border: 1px solid #34343a;
  border-left: 2px solid #326b80;
  border-radius: 4px;
  background: #252529;
}

.array-item-title {
  margin-bottom: 6px;
  color: #999999;
  font-size: 11px;
}

.array-number-row {
  display: flex;
  gap: 6px;
}

.array-number-row :deep(.el-input-number) {
  flex: 1;
}

.profile-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  gap: 6px;
  margin-bottom: 6px;
}

.profile-row :deep(.el-input-number) {
  width: 100%;
}

.subsection-title {
  margin-top: 12px;
}

.interaction-hint {
  padding: 7px 8px;
  border-left: 2px solid #35bfe8;
  background: rgba(53, 191, 232, 0.08);
  color: #8ca5b1;
  font-size: 11px;
  line-height: 1.5;
}

.danger-zone {
  padding-top: 8px;
  border-top: 1px solid #3e3e42;
}

.danger-zone :deep(.el-button) {
  width: 100%;
}

.property-row :deep(.el-input__wrapper) {
  background: #1e1e1e;
  border: 1px solid #3e3e42;
  color: #cccccc;
  font-size: 12px;
  border-radius: 2px;
  box-shadow: none;
  height: 28px;
}

.property-row :deep(.el-input__wrapper:hover),
.property-row :deep(.el-input__wrapper.is-focus) {
  border-color: #007acc;
  box-shadow: 0 0 0 1px #007acc inset;
}

.property-row :deep(.el-input__inner) {
  color: #cccccc;
  background: transparent;
}

.property-row :deep(.el-input-number .el-input__wrapper) {
  padding-right: 8px;
}

.axis-input {
  min-width: 0;
}

.axis-label {
  display: block;
  margin: 0 0 4px 2px;
  color: #718995;
  font-size: 10px;
  line-height: 1;
  text-transform: uppercase;
}

.vector-inputs :deep(.el-input-number) {
  width: 100%;
}

.vector-inputs :deep(.el-input__wrapper) {
  min-height: 28px;
  padding: 0 7px;
  border: 1px solid #3b3d45;
  border-radius: 4px;
  background: #18191d;
  box-shadow: none;
}

.vector-inputs :deep(.el-input__wrapper:hover) {
  border-color: #4e7080;
}

.vector-inputs :deep(.el-input__wrapper.is-focus) {
  border-color: #35bfe8;
  box-shadow: 0 0 0 1px rgba(53, 191, 232, 0.28) inset;
}

.vector-inputs :deep(.el-input__inner) {
  color: #d9e3e8;
  font-size: 11px;
  text-align: center;
}
</style>
