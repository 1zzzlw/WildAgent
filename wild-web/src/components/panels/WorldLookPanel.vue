<template>
  <div class="look-panel">
    <div class="panel-header">世界光影设置</div>
    <div class="panel-body">
      <div class="hint">
        光影与天气作用于整个世界；导入 .wildlook 后需要明确启用，不会自动覆盖当前设置。
      </div>
      <WorldPackagePanel mode="look" />
    </div>
  </div>
</template>

<script setup lang="ts">
import WorldPackagePanel from './WorldPackagePanel.vue'
</script>

<style scoped>
.look-panel { display: flex; height: 100%; flex-direction: column; color: #cccccc; }
.panel-header { padding: 8px 12px; border-bottom: 1px solid #3e3e42; font-size: 13px; font-weight: 500; }
.panel-body { display: flex; min-height: 0; flex: 1; flex-direction: column; gap: 8px; overflow-y: auto; padding: 10px; }
.hint { color: #8f8f96; font-size: 11px; line-height: 1.5; }
</style>
