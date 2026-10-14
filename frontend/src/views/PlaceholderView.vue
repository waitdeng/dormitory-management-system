<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<template>
  <el-empty :description="title">
    <div class="placeholder-body">
      <p>{{ description || '该模块将在后续里程碑接入真实数据与业务流程。' }}</p>
    </div>
  </el-empty>
</template>

<style scoped>
.placeholder-body {
  color: #909399;
  font-size: 13px;
}
</style>
