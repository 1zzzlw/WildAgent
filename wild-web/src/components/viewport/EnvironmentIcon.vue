<template>
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" :data-environment="preset">
    <g v-if="preset === 'minimal'">
      <path d="M3 9h18M3 20h18M6 9l-3 11M10 9l-1 11M14 9l1 11M18 9l3 11M4.5 14h15" />
    </g>
    <g v-else-if="preset === 'meadow'">
      <path d="M3 20h18M7 20V9m0 6-4-4m4 6 4-5M17 20V7m0 7-4-4m4 6 4-5M12 20v-3" />
    </g>
    <g v-else-if="preset === 'alpine'">
      <path d="m2 20 8-15 6 11 3-6 4 10H2Zm5-9 3 2 3-2m3 5 3 4" />
    </g>
    <g v-else-if="preset === 'desert'">
      <circle cx="17" cy="5" r="2" />
      <path d="M2 18c5-7 10 5 20-2M2 21h20M8 16V5a1.5 1.5 0 0 0-3 0v5m3 2h3V8M5 10H3V7" />
    </g>
    <g v-else-if="preset === 'autumn'">
      <path d="M12 21V11m0 5-4-3m4 1 3-3M6 15a4 4 0 0 1-1-7 4 4 0 0 1 7-4 4 4 0 0 1 7 4 4 4 0 0 1-1 7M9 21h6" />
      <path d="M20 18c-2 0-3 1-3 3 2 0 3-1 3-3Z" />
    </g>
  </svg>
</template>

<script setup lang="ts">
import type { EnvironmentPresetId } from '../../renderer/defaultWorldLook'

withDefaults(defineProps<{ preset?: EnvironmentPresetId }>(), { preset: 'alpine' })
</script>
