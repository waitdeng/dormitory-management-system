<script setup lang="ts">
import BasePlaceholder from '@/views/PlaceholderView.vue'
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<template>
  <BasePlaceholder :title="(route.meta.title as string) || '待建设'" />
</template>
