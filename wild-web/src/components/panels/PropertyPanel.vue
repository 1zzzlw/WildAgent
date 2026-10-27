<template>
  <div class="property-panel">
    <div class="panel-header">
      <span>属性面板</span>
      <el-button v-if="selectedItem" size="small" plain :disabled="!rotationOperations.length || sceneStore.isReconstructing"
        title="支持单选有朝向的构件；门窗请旋转直线宿主墙。带附件的楼板/屋顶及世界坐标附件暂不支持整体旋转" @click="rotateSelectedItem">
        旋转 90°
      </el-button>
      <el-button v-if="removalOperations.length" size="small" type="danger" plain
        :loading="isRemoving" :disabled="sceneStore.isReconstructing" @click="removeSelectedItems">
        {{ removalOperations.length > 1 ? `删除选中 (${removalOperations.length})` : '删除构件' }}
      </el-button>
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
                <div class="behavior-description">开启后可双击进入移动</div>
              </div>
              <el-switch :model-value="selectedComponent.draggable !== false" inline-prompt
                active-text="开" inactive-text="关" @change="handleDraggableEnabled" />
            </div>
            <div class="interaction-hint">单击高亮，双击显示移动控件；移动宿主时附件跟随，修改支持撤销重做。</div>
            <div v-if="coordinateHint" class="interaction-hint">{{ coordinateHint }}</div>
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
                <div v-for="(axis, index) in wallAxes" :key="axis" class="axis-input">
                  <span class="axis-label wall-axis-label">{{ axis }}</span>
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
                <el-option v-for="name in componentMaterialNames('frameMaterial')" :key="name" :label="materialDisplayName(name)" :value="name" />
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
              <label>帘片分节</label>
              <el-input-number :model-value="componentOptionalNumber('leafRows')" :min="1" :max="8" :step="1"
                placeholder="自动"
                @change="(value: number | undefined) => handleComponentIntegerChange('leafRows', value)" />
            </div>
            <div class="property-row">
              <label>门扇材质</label>
              <el-select :model-value="componentString('leafMaterial')" placeholder="未指定"
                @change="(value: string) => handleComponentChange('leafMaterial', value)">
                <el-option v-for="name in componentMaterialNames('leafMaterial')" :key="name" :label="materialDisplayName(name)" :value="name" />
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
                <el-option v-for="name in componentMaterialNames('glassMaterial')" :key="name" :label="materialDisplayName(name)" :value="name" />
              </el-select>
            </div>
          </div>

          <div v-if="selectedComponent.type === 'door' || selectedComponent.type === 'window' || selectedComponent.type === 'bay_window'"
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
                  <el-option v-if="selectedComponent.type === 'door'" label="向上卷帘" value="lift" />
                </el-select>
              </div>
              <div v-if="selectedComponent.type === 'door' && componentInteraction.mode !== 'lift'" class="property-row">
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
                <label>{{ componentInteraction.mode === 'lift' ? '上移距离' : '推拉距离' }}</label>
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
              <div class="interaction-hint">{{ selectedComponent.type !== 'door'
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

          <div v-if="selectedComponent.type === 'fan' || selectedComponent.type === 'elevator'" class="property-section">
            <div class="section-title">{{ selectedComponent.type === 'fan' ? '吊扇参数' : '电梯参数' }}</div>
            <div v-for="key in selectedComponent.type === 'fan' ? ['position', 'controlPosition'] : ['position']" :key="key" class="property-row vector-property">
              <label>{{ key === 'controlPosition' ? '开关位置' : '设备位置' }}</label>
              <div class="vector-inputs"><div v-for="(axis, index) in axes" :key="axis" class="axis-input">
                <span class="axis-label">{{ axis }}</span>
                <el-input-number :model-value="componentVectorValue(key, index)" :controls="false" :step="0.1"
                  @change="(value: number | undefined) => handleComponentVectorChange(key, index, value)" />
              </div></div>
            </div>
            <div v-for="field in mechanismNumberFields" :key="field.key" class="property-row">
              <label>{{ field.label }}</label>
              <el-input-number :model-value="mechanismNumberValue(field.key, field.defaultValue)" :min="field.min" :max="field.max" :step="field.step"
                @change="(value: number | undefined) => handleMechanismNumberChange(field.key, value)" />
            </div>
            <div v-if="selectedComponent.type === 'fan'" class="property-row">
              <label>初始运行</label><el-switch :model-value="selectedComponent.initiallyOn ?? false"
                @change="(value: boolean) => handleComponentChange('initiallyOn', value)" />
            </div>
            <div v-for="field in mechanismMaterialFields" :key="field.key" class="property-row">
              <label>{{ field.label }}</label>
              <el-select :model-value="componentString(field.key)" placeholder="默认材质" @change="(value: string) => handleComponentChange(field.key, value)">
                <el-option v-for="name in componentMaterialNames(field.key)" :key="name" :label="materialDisplayName(name)" :value="name" />
              </el-select>
            </div>
            <div class="interaction-hint">{{ selectedComponent.type === 'fan'
              ? '点击开关循环：关闭 → 低速 → 高速。位置是电机中心，吊杆向上连接天花；开关位置可单独调整。'
              : '点击层门旁按钮呼梯，轿内数字选层，箭头开关门。入口朝 +Z；请为井道围墙和上层楼板留出通道。位置 Y 是初始停靠层地板高度。' }}</div>
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
                <el-option v-for="name in componentMaterialNames(materialField.key)" :key="name" :label="materialDisplayName(name)" :value="name" />
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
                <el-option v-for="name in componentMaterialNames('material')" :key="name" :label="materialDisplayName(name)" :value="name" />
              </el-select>
            </div>
            <div class="property-row">
              <label>栏杆材质</label>
              <el-select :model-value="componentString('railingMaterial')" placeholder="未指定"
                @change="(value: string) => handleComponentChange('railingMaterial', value)">
                <el-option v-for="name in componentMaterialNames('railingMaterial')" :key="name" :label="materialDisplayName(name)" :value="name" />
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
                <el-option v-for="name in componentMaterialNames('glassMaterial')" :key="name" :label="materialDisplayName(name)" :value="name" />
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
                <el-option v-for="name in componentMaterialNames(materialField.key)" :key="name" :label="materialDisplayName(name)" :value="name" />
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
                <el-option v-for="name in componentMaterialNames('material')" :key="name" :label="materialDisplayName(name)" :value="name" />
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
                <el-option v-for="name in componentMaterialNames(materialField.key)" :key="name" :label="materialDisplayName(name)" :value="name" />
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
                <el-option v-for="name in componentMaterialNames('material')" :key="name" :label="materialDisplayName(name)" :value="name" />
              </el-select>
            </div>
            <div class="property-row">
              <label>栏板类型</label>
              <el-select :model-value="componentString('infillType') || ''" placeholder="无栏板" clearable
                @clear="clearComponentField('infillType')"
                @change="(value: string) => handleComponentChange('infillType', value)">
                <el-option label="玻璃" value="glass" />
                <el-option label="实心板" value="panel" />
              </el-select>
            </div>
            <div v-if="componentString('infillType')" class="property-row">
              <label>栏板厚度</label>
              <el-input-number :model-value="componentOptionalNumber('infillThickness',
                componentString('infillType') === 'glass' ? 0.02 : 0.05)"
                :min="0.001" :step="0.005"
                @change="(value: number | undefined) => handleComponentNumberChange('infillThickness', value)" />
            </div>
            <div v-if="componentString('infillType')" class="property-row">
              <label>栏板高度比例</label>
              <el-input-number :model-value="componentOptionalNumber('infillTopRatio', 0.92)"
                :min="0.01" :max="1" :step="0.02"
                @change="(value: number | undefined) => handleComponentNumberChange('infillTopRatio', value)" />
            </div>
            <div v-if="componentString('infillType')" class="property-row">
              <label>栏板材质</label>
              <el-select :model-value="componentString('infillMaterial')" :placeholder="componentString('infillType') === 'glass' ? '默认玻璃' : '继承构件材质'" clearable
                @clear="clearComponentField('infillMaterial')"
                @change="(value: string) => handleComponentChange('infillMaterial', value)">
                <el-option v-for="name in componentMaterialNames('infillMaterial')" :key="name" :label="materialDisplayName(name)" :value="name" />
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
        </template>

        <div class="property-section" v-if="selectedPrimitive?.shape === 'box'">
          <div class="section-title">招牌文字</div>
          <div class="property-row">
            <label>文字</label>
            <el-input :model-value="selectedPrimitive.label?.text || ''" aria-label="招牌文字" maxlength="256"
              placeholder="输入建筑名称；清空移除文字" @focus="beginLabelEdit" @blur="labelEditGroup = undefined"
              @input="changeLabelText" />
          </div>
          <div class="interaction-hint">文字位于构件正面，随构件移动、旋转，并保存在 WILD 文件中。</div>
        </div>
        <div class="property-section" v-if="selectedPrimitive">
          <div class="section-title">真实光源</div>
          <div class="property-row">
            <label>照亮周围</label>
            <el-switch :model-value="!!selectedPrimitive.lightSource" aria-label="照亮周围" @change="togglePrimitiveLight" />
          </div>
          <template v-if="selectedPrimitive.lightSource">
            <div class="property-row">
              <label>灯光强度</label>
              <el-input-number :model-value="selectedPrimitive.lightSource.intensity ?? 25" :min="0" :step="5"
                aria-label="自定义灯光强度" @change="(value: number | undefined) => changePrimitiveLight('intensity', value)" />
            </div>
            <div class="property-row">
              <label>照射距离</label>
              <el-input-number :model-value="selectedPrimitive.lightSource.distance ?? 8" :min="0.1" :step="0.5"
                @change="(value: number | undefined) => changePrimitiveLight('distance', value)" />
            </div>
          </template>
          <div class="interaction-hint">可给任意自制灯罩或灯泡绑定光源；右键切换关灯、弱光与强光。</div>
        </div>
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

        <div class="property-section" v-if="selectedElement?.type === 'furniture'">
          <div class="section-title">家具参数</div>
          <div class="property-row">
            <label>子类型</label>
            <el-select :model-value="(selectedElement as any).subtype || 'table'"
              @change="(value: string) => handleFurnitureSubtype(value)">
              <el-option v-for="item in furnitureSubtypes" :key="item.value"
                :label="item.label" :value="item.value" />
            </el-select>
          </div>
          <div class="property-row">
            <label>宽</label>
            <el-input-number :model-value="furnitureDimension('width')" :min="0.01" :step="0.05"
              @change="(value: number | undefined) => handleFurnitureDimension('width', value)" />
          </div>
          <div class="property-row">
            <label>深</label>
            <el-input-number :model-value="furnitureDimension('depth')" :min="0.01" :step="0.05"
              @change="(value: number | undefined) => handleFurnitureDimension('depth', value)" />
          </div>
          <div class="property-row">
            <label>高</label>
            <el-input-number :model-value="furnitureDimension('height')" :min="0.01" :step="0.05"
              @change="(value: number | undefined) => handleFurnitureDimension('height', value)" />
          </div>
          <div class="property-row">
            <label>朝向（度）</label>
            <el-input-number :model-value="furnitureYawDegrees" :step="15"
              @change="(value: number | undefined) => handleFurnitureYaw(value)" />
          </div>
          <div class="interaction-hint">
            正面朝 +Z（椅/沙发靠背、床头板在 −Z 侧）。转向绕家具自身的底面中心，
            位置不会跟着挪动。“高”的含义逐子类型不同：桌/柜是台面顶高，椅/沙发是含靠背的总高。
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { getComponentCompiler, resolveOpeningInteractionSpec } from 'wild-core/compiler'
import { getGeometryReferences } from 'wild-core/relationships'
import { acceptsComponentMaterial } from '../../wild/materialCompatibility'
import { SURFACE_MATERIAL_PRESETS } from '../../wild/surfaceMaterialPresets'
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSceneStore } from '../../stores/sceneStore'
import { useSelectionStore } from '../../stores/selectionStore'
import { createPatch, createGeometryRemovalOperations } from '../../wild/scenePatch'
import { createGeometryRotationOperations } from '../../wild/componentDrag'
import type { PrimitiveParams } from 'wild-core/types'
import type { SceneOperation } from '../../types/scenePatch'

const sceneStore = useSceneStore()
const selectionStore = useSelectionStore()
const isRemoving = ref(false)
const removalOperations = computed(() => sceneStore.document
  ? createGeometryRemovalOperations(sceneStore.document.blueprint, selectionStore.selectedIds)
  : [])
const rotationOperations = computed(() => sceneStore.document
  ? createGeometryRotationOperations(sceneStore.document.blueprint, selectionStore.selectedIds)
  : [])

async function rotateSelectedItem() {
  if (!sceneStore.document || !rotationOperations.value.length) return
  const patch = createPatch(
    sceneStore.document.revision,
    rotationOperations.value,
    'user',
    false,
    `旋转${selectionStore.selectedIds[0]} 90°`,
  )
  if (!await sceneStore.applyPatch(patch)) ElMessage.error('旋转未能应用，请查看场景校验结果')
}
const axes = ['X', 'Y', 'Z'] as const
const wallAxes = ['沿墙', '世界Y', '法向'] as const
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

const mechanismNumberFields = computed(() => selectedComponent.value?.type === 'fan' ? [
  { key: 'radius', label: '扇叶半径', min: 0.1, max: undefined, step: 0.05, defaultValue: 0.65 },
  { key: 'bladeCount', label: '扇叶数量', min: 3, max: 8, step: 1, defaultValue: 4 },
  { key: 'drop', label: '吊杆长度', min: 0.01, max: undefined, step: 0.05, defaultValue: 0.25 },
  { key: 'rpm', label: '高速转速', min: 1, max: 600, step: 10, defaultValue: 180 },
] : [
  { key: 'width', label: '轿厢宽度', min: 1.2, max: undefined, step: 0.1, defaultValue: 1.8 },
  { key: 'depth', label: '轿厢深度', min: 1.2, max: undefined, step: 0.1, defaultValue: 1.8 },
  { key: 'height', label: '轿厢高度', min: 2.1, max: undefined, step: 0.1, defaultValue: 2.5 },
  { key: 'floorHeight', label: '楼层间距', min: 2.3, max: undefined, step: 0.1, defaultValue: 3.3 },
  { key: 'floorCount', label: '楼层数量', min: 1, max: undefined, step: 1, defaultValue: 2 },
  { key: 'initialFloor', label: '初始层序（0起）', min: 0, max: (selectedComponent.value?.type === 'elevator' ? selectedComponent.value.floorCount : 1) - 1, step: 1, defaultValue: 0 },
])
const mechanismMaterialFields = computed(() => selectedComponent.value?.type === 'fan'
  ? [{ key: 'material', label: '扇叶材质' }, { key: 'frameMaterial', label: '机身材质' }]
  : [{ key: 'material', label: '轿厢内饰' }, { key: 'frameMaterial', label: '框架材质' }, { key: 'doorMaterial', label: '门板材质' }, { key: 'floorMaterial', label: '地板材质' }])
function mechanismNumberValue(key: string, fallback: number): number {
  const c = selectedComponent.value
  return c?.type === 'elevator' && ['width', 'depth', 'height'].includes(key)
    ? c.dimensions[key as keyof typeof c.dimensions] : componentNumber(key, fallback)
}
function handleMechanismNumberChange(key: string, value: number | undefined) {
  if (value === undefined || !Number.isFinite(value)) return
  const c = selectedComponent.value
  if (c?.type === 'elevator' && ['width', 'depth', 'height'].includes(key)) {
    void applyComponentChanges({ dimensions: { ...c.dimensions, [key]: value } }, '修改轿厢尺寸')
  } else if (['bladeCount', 'floorCount', 'initialFloor'].includes(key)) handleComponentIntegerChange(key, value)
  else handleComponentNumberChange(key, value)
}

const selectedElement = computed(() => {
  const id = selectionStore.selectedIds[0]
  if (!id || !sceneStore.document) return null
  return sceneStore.document.blueprint.geometry.elements.find(e => e.id === id) || null
})

const selectedItem = computed(() => selectedComponent.value || selectedElement.value)
const selectedPrimitive = computed(() => selectedElement.value?.type === 'primitive' ? selectedElement.value as unknown as PrimitiveParams : null)
const editing = computed(() => selectedComponent.value ? getComponentCompiler(selectedComponent.value.type)?.editing : undefined)
const hasWallAttachment = computed(() => editing.value?.translation === 'wallFrom')
const hasOpeningHeight = computed(() => hasWallAttachment.value && editing.value?.parameters.includes('height'))
const hasFrame = computed(() => editing.value?.parameters.includes('frameWidth'))
const coordinateHint = computed(() => {
  const ref = selectedComponent.value && getGeometryReferences(selectedComponent.value)[0]
  if (!ref) return ''
  if (ref.field === 'parentWall') return '位置依次为沿墙距离、底部世界高度、墙面法向偏移（米）。'
  if (ref.field === 'parentFloor') return '坐标相对父楼板顶面原点；移动父楼板会带动本构件。'
  if (ref.field === 'parentRoof') return '坐标相对父屋顶中心与屋面高度；移动屋顶会带动本构件。'
  return ''
})
const walls = computed(() => (
  sceneStore.document?.blueprint.geometry.elements.filter(element => element.type === 'wall') || []
))
const floors = computed(() => (
  sceneStore.document?.blueprint.geometry.elements.filter(element => element.type === 'floor') || []
))
const roofs = computed(() => (
  sceneStore.document?.blueprint.geometry.elements.filter(element => element.type === 'roof') || []
))
function componentMaterialNames(field: string) {
  const component = selectedComponent.value
  const materials = { ...Object.fromEntries(SURFACE_MATERIAL_PRESETS.map(p => [p.id, p.material])),
    ...sceneStore.document?.blueprint.materials }
  return Object.entries(materials)
    .filter(([name, material]) => !component || acceptsComponentMaterial(component, field, name, material))
    .map(([name]) => name)
}
function materialDisplayName(name: string) {
  return sceneStore.document?.blueprint.materials?.[name]
    ? name : SURFACE_MATERIAL_PRESETS.find(p => p.id === name)?.name || name
}
const railLevels = computed(() => (
  selectedComponent.value?.type === 'railing'
    ? selectedComponent.value.railLevels || [1]
    : []
))
const componentInteraction = computed(() => {
  if (selectedComponent.value?.type === 'door' || selectedComponent.value?.type === 'window' || selectedComponent.value?.type === 'bay_window') {
    return resolveOpeningInteractionSpec(selectedComponent.value.type, selectedComponent.value.interaction) || null
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

// ── 家具元素 ──
// dimensions 是嵌套对象、rotation 是数组，都不能走 handleChange 的扁平数字写回
// （update_element 是浅合并：整块替换 dimensions / rotation，正是这里需要的语义）。
const furnitureSubtypes = [
  { value: 'table', label: '桌' },
  { value: 'chair', label: '椅' },
  { value: 'sofa', label: '沙发' },
  { value: 'bookshelf', label: '书架' },
  { value: 'bed', label: '床' },
  { value: 'wardrobe', label: '衣柜' },
  { value: 'nightstand', label: '床头柜' },
  { value: 'tv_cabinet', label: '电视柜' },
  { value: 'lamp', label: '灯（静态，不发光）' },
  { value: 'tile', label: '薄板' },
] as const

function furnitureDimension(key: 'width' | 'depth' | 'height'): number | undefined {
  const dimensions = (selectedElement.value as any)?.dimensions
  const value = dimensions && typeof dimensions === 'object' ? dimensions[key] : undefined
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

const furnitureYawDegrees = computed(() => {
  const rotation = (selectedElement.value as any)?.rotation
  if (!Array.isArray(rotation) || typeof rotation[1] !== 'number') return 0
  return Math.round((rotation[1] * 180) / Math.PI)
})

function handleFurniturePatch(changes: Record<string, unknown>, summary: string) {
  if (!selectedElement.value || !sceneStore.document) return
  const patch = createPatch(
    sceneStore.document.revision,
    [{ op: 'update_element', id: selectedElement.value.id, changes }],
    'user',
    false,
    summary,
  )
  sceneStore.applyPatch(patch)
}

let labelEditGroup: string | undefined
let labelEditSequence = 0
function beginLabelEdit() {
  labelEditGroup = `label:${sceneStore.document?.id}:${selectedPrimitive.value?.id}:${++labelEditSequence}`
}
function changeLabelText(text: string) {
  if (!selectedPrimitive.value || !sceneStore.document) return
  if (!labelEditGroup) beginLabelEdit()
  const label = text.trim() ? { ...selectedPrimitive.value.label, text } : undefined
  const patch = createPatch(sceneStore.document.revision,
    [{ op: 'update_element', id: selectedPrimitive.value.id, changes: { label } }], 'user', false, '修改招牌文字')
  void sceneStore.applyPatch(patch, labelEditGroup)
}

function togglePrimitiveLight(enabled: string | number | boolean) {
  handleFurniturePatch({ lightSource: enabled ? { intensity: 25, distance: 8, initiallyOn: true } : undefined }, '修改自定义光源')
}

function changePrimitiveLight(key: 'intensity' | 'distance', value: number | undefined) {
  if (value === undefined || !Number.isFinite(value)) return
  handleFurniturePatch({ lightSource: { ...selectedPrimitive.value?.lightSource, [key]: value } }, '修改自定义光源')
}

function handleFurnitureSubtype(value: string) {
  if (!value) return
  handleFurniturePatch({ subtype: value }, `修改${selectedElement.value?.id}.subtype`)
}

function handleFurnitureDimension(
  key: 'width' | 'depth' | 'height',
  value: number | undefined,
) {
  const current = (selectedElement.value as any)?.dimensions
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return
  handleFurniturePatch(
    { dimensions: { ...(current && typeof current === 'object' ? current : {}), [key]: value } },
    `修改${selectedElement.value?.id}.dimensions.${key}`,
  )
}

function handleFurnitureYaw(value: number | undefined) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return
  const current = (selectedElement.value as any)?.rotation
  const rotation = Array.isArray(current) ? [...current] : [0, 0, 0]
  rotation[1] = (value * Math.PI) / 180
  handleFurniturePatch({ rotation }, `修改${selectedElement.value?.id}.rotation`)
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

async function applyComponentChanges(changes: Record<string, unknown>, summary: string, prefix: SceneOperation[] = []) {
  if (!selectedComponent.value || !sceneStore.document) return
  const patch = createPatch(
    sceneStore.document.revision,
    [...prefix, { op: 'update_component', id: selectedComponent.value.id, changes }],
    'user',
    false,
    summary,
  )
  if (!await sceneStore.applyPatch(patch)) ElMessage.error('参数不符合组件约束，修改未应用')
}

function handleComponentChange(key: string, value: unknown) {
  if (value === undefined || value === null || value === '') return
  const prefix: SceneOperation[] = []
  if (typeof value === 'string' && (key === 'material' || key.endsWith('Material'))) {
    const existing = sceneStore.document?.blueprint.materials?.[value]
    const material = existing || SURFACE_MATERIAL_PRESETS.find(p => p.id === value)?.material
    if (!material || !selectedComponent.value || !acceptsComponentMaterial(selectedComponent.value, key, value, material)) {
      ElMessage.warning('请选择与该部位匹配的材质')
      return
    }
    if (!existing) prefix.push({ op: 'upsert_material', name: value, material: JSON.parse(JSON.stringify(material)) })
  }
  const changes: Record<string, unknown> = { [key]: value }
  if (key === 'infillType' && selectedComponent.value?.type === 'railing') {
    const name = selectedComponent.value.infillMaterial
    const material = name && sceneStore.document?.blueprint.materials?.[name]
    if (name && material && !acceptsComponentMaterial({ ...selectedComponent.value, infillType: value } as typeof selectedComponent.value, 'infillMaterial', name, material)) {
      changes.infillMaterial = undefined
    }
  }
  void applyComponentChanges(changes, `修改${selectedComponent.value?.id}.${key}`, prefix)
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
  const component = selectedComponent.value
  if (!component || !['door', 'window', 'bay_window'].includes(component.type)) return
  void applyComponentChanges(
    { interaction: enabled ? undefined : false },
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

async function removeSelectedItems() {
  if (!sceneStore.document || !removalOperations.value.length || isRemoving.value || sceneStore.isReconstructing) return
  const documentId = sceneStore.document.id
  const selectedIds = [...selectionStore.selectedIds]
  isRemoving.value = true
  try {
    const target = removalOperations.value.length === 1
      ? removalOperations.value[0]!.id
      : `选中的 ${removalOperations.value.length} 个构件`
    await ElMessageBox.confirm(`确定删除 ${target}？依附这些构件的门窗等也会一并删除，可通过撤销恢复。`, '删除构件', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    if (!sceneStore.document || sceneStore.document.id !== documentId || sceneStore.isReconstructing) return
    const operations = createGeometryRemovalOperations(sceneStore.document.blueprint, selectedIds)
    if (!operations.length) return
    const patch = createPatch(sceneStore.document.revision, operations, 'user', false, `删除 ${operations.length} 个构件`)
    if (await sceneStore.applyPatch(patch)) {
      selectionStore.clearSelection()
      selectionStore.setHovered(null)
      ElMessage.success('构件已删除，可撤销恢复')
    } else {
      ElMessage.error('删除失败，请查看场景校验结果')
    }
  } catch {
    return
  } finally {
    isRemoving.value = false
  }
}
</script>

<style scoped>
.wall-axis-label { width: auto; min-width: 3em; }
.property-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 500;
  border-bottom: 1px solid var(--studio-border);
}

.panel-body {
  flex: 1;
  overflow-y: auto;
}

.empty-state {
  padding: 24px;
  text-align: center;
  color: var(--studio-muted);
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
  border: 1px solid var(--studio-border);
  border-radius: 6px;
  background: linear-gradient(145deg, var(--studio-surface), var(--studio-surface));
}

.behavior-row {
  justify-content: space-between;
}

.behavior-row > div:first-child {
  min-width: 0;
}

.behavior-description {
  margin-top: 2px;
  color: var(--studio-muted);
  font-size: 10px;
}

.behavior-card :deep(.el-switch) {
  flex: 0 0 auto;
  --el-switch-on-color: var(--studio-accent);
  --el-switch-off-color: var(--studio-muted);
}

.section-title {
  font-size: 12px;
  font-weight: 500;
  color: var(--studio-muted);
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
  border: 1px solid var(--studio-accent-border);
  border-radius: 4px;
  background: var(--studio-hover);
  color: var(--studio-accent);
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
  border: 1px solid var(--studio-border);
  border-left: 2px solid var(--studio-accent-border);
  border-radius: 4px;
  background: var(--studio-surface);
}

.array-item-title {
  margin-bottom: 6px;
  color: var(--studio-muted);
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
  border-left: 2px solid var(--studio-accent-border);
  background: var(--studio-hover);
  color: var(--studio-muted);
  font-size: 11px;
  line-height: 1.5;
}

.property-row :deep(.el-input__wrapper) {
  background: var(--studio-input);
  border: 1px solid var(--studio-border);
  color: var(--studio-text);
  font-size: 12px;
  border-radius: 2px;
  box-shadow: none;
  height: 28px;
}

.property-row :deep(.el-input__wrapper:hover),
.property-row :deep(.el-input__wrapper.is-focus) {
  border-color: var(--studio-accent-border);
  box-shadow: 0 0 0 1px rgba(41, 76, 61, 0.12) inset;
}

.property-row :deep(.el-input__inner) {
  color: var(--studio-text);
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
  color: var(--studio-muted);
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
  border: 1px solid var(--studio-border);
  border-radius: 4px;
  background: var(--studio-input);
  box-shadow: none;
}

.vector-inputs :deep(.el-input__wrapper:hover) {
  border-color: var(--studio-accent-border);
}

.vector-inputs :deep(.el-input__wrapper.is-focus) {
  border-color: var(--studio-accent-border);
  box-shadow: 0 0 0 1px rgba(41, 76, 61, 0.12) inset;
}

.vector-inputs :deep(.el-input__inner) {
  color: var(--studio-text);
  font-size: 11px;
  text-align: center;
}
</style>
