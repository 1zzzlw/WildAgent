<template>
  <RouterView v-slot="{ Component }">
    <KeepAlive include="WorkbenchView">
      <component :is="Component" />
    </KeepAlive>
  </RouterView>
</template>

<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>
