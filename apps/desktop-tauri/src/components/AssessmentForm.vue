<script setup>
import { reactive } from "vue";
import ErrorBanner from "./ErrorBanner.vue";
import { state, submitAssessment } from "../state/session.js";

const bodyPartOptions = [
  { value: "neck", label: "颈部" },
  { value: "shoulder", label: "肩部" },
  { value: "upper_back", label: "上背" },
  { value: "low_back", label: "腰背" },
  { value: "hip", label: "髋部" },
  { value: "core", label: "核心" },
];

const form = reactive({
  body_parts: ["neck", "shoulder"],
  sedentary_minutes: 480,
  available_minutes: 10,
  pain_score: 3,
  acute_discomfort: false,
});

function togglePart(value) {
  const index = form.body_parts.indexOf(value);
  if (index >= 0) {
    if (form.body_parts.length > 1) form.body_parts.splice(index, 1);
  } else {
    form.body_parts.push(value);
  }
}

function onPainChange(event) {
  const target = event.target;
  const value = target.thumb ? target.thumb.value : target.value;
  if (value !== null && value !== undefined && value !== "") {
    form.pain_score = Number(value);
  }
}
</script>

<template>
  <m3e-card variant="elevated" class="surface-card">
    <div class="surface-body">
      <header class="page-head">
        <h1>评估</h1>
        <p>初次见面，请填写一些基本信息。这能帮助生成相对准确的建议和方案。</p>
      </header>

      <m3e-callout class="disclaimer medical-note">
        <span class="material-symbols-rounded" slot="icon">medical_information</span>
        <span slot="label">指导提示</span>
        <p>
          本产品为健康行为指导工具，不提供医疗诊断或治疗建议。<br>
          如出现持续疼痛、放射痛、麻木加重、肢体无力或外伤后剧痛，请及时就医。
        </p>
      </m3e-callout><br>

      <m3e-list variant="segmented" class="assessForm">
        <m3e-list-item>
          <span class="material-symbols-rounded" slot="leading">avg_time</span>
          时间安排
        </m3e-list-item>
        <m3e-list-item>
          每日久坐时长
          <span slot="supporting-text">每天久坐的时间大致总和</span>
          <m3e-form-field variant="filled" class="field" slot="trailing">
            <input id="sedentary-minutes" v-model.number="form.sedentary_minutes" type="number" min="0" max="1440" />
            <span slot="suffix-text">分钟</span>
          </m3e-form-field>
        </m3e-list-item>
        <m3e-list-item>
          每次休息可用时长
          <span slot="supporting-text">您希望休息阶段的时长</span>
          <m3e-form-field variant="filled" class="field" slot="trailing">
            <input id="available-minutes" v-model.number="form.available_minutes" type="number" min="1" max="120" />
            <span slot="suffix-text">分钟</span>
          </m3e-form-field>
        </m3e-list-item>
      </m3e-list>

      <m3e-list variant="segmented">
        <m3e-list-item>
          <span class="material-symbols-rounded" slot="leading">exercise</span>
          身体情况
        </m3e-list-item>

        <m3e-list-item>
          另外，在下面的部位里，您有哪些部位不太舒服？<br><br>
          <m3e-chip-set class="chips">
            <m3e-filter-chip v-for="option in bodyPartOptions" :key="option.value" :value="option.value"
              :selected.prop="form.body_parts.includes(option.value)" @change="togglePart(option.value)">
              {{ option.label }}
            </m3e-filter-chip>
          </m3e-chip-set>
        </m3e-list-item>
        <m3e-list-item>
          就您来说，最严重的部分有多痛？<br>
          <m3e-slider class="slider" max="10" step="1" @input="onPainChange" @change="onPainChange">
            <m3e-slider-thumb :value.prop="form.pain_score"></m3e-slider-thumb>
          </m3e-slider>

          <div class="slider-head">
            <span class="field-label"></span>
            <span class="value mono">{{ form.pain_score }}<small> / 10</small></span>
          </div>
        </m3e-list-item>
        <m3e-list-item>
          <m3e-checkbox :checked.prop="form.acute_discomfort" @change="form.acute_discomfort = $event.target.checked"
            slot="leading"></m3e-checkbox>
          我现在就有明显的酸痛等不适症状
        </m3e-list-item>
      </m3e-list>

      <ErrorBanner :error="state.error" />

      <m3e-button class="block" variant="filled" size="medium" :disabled.prop="state.busy"
        @click="submitAssessment(form)">
        {{ state.busy ? "提交中…" : "生成干预计划" }}
      </m3e-button>
    </div>
  </m3e-card>
</template>

<style scoped>
m3e-list.assessForm {
  margin-bottom: 1rem;

  --m3e-form-field-font-size:1.4rem
}

.field {
  width: 14rem;
  margin-top: 1.4rem;
}

.field-label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.slider-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.value {
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--md-sys-color-secondary);
}

.value small {
  color: var(--md-sys-color-outline);
  font-size: 1rem;
  font-weight: 400;
}

.slider {
  display: block;
  width: 100%;
  margin: 12px 0 0;
  --m3e-slider-min-width: 100%;
  --m3e-slider-tick-size: 3px;
}

.checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 2px 0 20px;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 13px;
  cursor: pointer;
}

.block {
  width: 100%;
  margin-top: 2rem;
}
</style>
