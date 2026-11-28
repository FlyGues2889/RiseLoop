<script setup>
import { computed } from "vue";
import DOMPurify from "dompurify";
import { marked } from "marked";

const props = defineProps({
  text: { type: String, default: "" },
});

// 模型输出直接进 webview，必须清洗；只放行正文需要的标签
const html = computed(() =>
  DOMPurify.sanitize(marked.parse(String(props.text ?? ""), { async: false }), {
    ALLOWED_TAGS: ["p", "strong", "em", "ul", "ol", "li", "br", "code"],
    ALLOWED_ATTR: [],
  })
);
</script>

<template>
  <div class="markdown" v-html="html"></div>
</template>

<style scoped>
.markdown {
  font-size: 0.875rem;
  line-height: 1.75;
}

.markdown :deep(p) {
  margin: 0 0 0.5rem;
}

.markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown :deep(ul),
.markdown :deep(ol) {
  margin: 0.25rem 0 0.5rem;
  padding-left: 1.15rem;
}

.markdown :deep(:last-child) {
  margin-bottom: 0;
}
</style>
