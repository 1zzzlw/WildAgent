<template>
  <nav class="admin-pagination" aria-label="列表分页">
    <span>共 {{ total }} 条 · 第 {{ page }} / {{ Math.max(1, Math.ceil(total / pageSize)) }} 页</span>
    <div>
      <button class="admin-button" :disabled="busy || page <= 1" @click="$emit('change', page - 1)">上一页</button>
      <button class="admin-button" :disabled="busy || page * pageSize >= total" @click="$emit('change', page + 1)">下一页</button>
    </div>
  </nav>
</template>
<script setup lang="ts">
withDefaults(defineProps<{ page: number; total: number; pageSize?: number; busy?: boolean }>(), { pageSize: 20 })
defineEmits<{ change: [page: number] }>()
</script>
