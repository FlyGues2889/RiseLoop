<script setup>
import { reactive } from "vue";
import ErrorBanner from "./ErrorBanner.vue";
import LoadingOverlay from "./LoadingOverlay.vue";
import MedicalNote from "./MedicalNote.vue";
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
        <h1>你的情况</h1>
        <p class="lead">花一分钟填完这几项，方案会按你每天能坐多久、每次能挤出多少时间来匹配。</p>
      </header>

      <MedicalNote />

      <m3e-list variant="segmented" class="assessForm">
        <m3e-list-item>
          <span class="material-symbols-rounded" slot="leading">avg_time</span>
          时间安排
        </m3e-list-item>
        <m3e-list-item>
          每日久坐时长
          <m3e-form-field variant="filled" class="field" slot="trailing">
            <input id="sedentary-minutes" v-model.number="form.sedentary_minutes" type="number" min="0" max="1440" />
            <span slot="suffix-text">分钟</span>
          </m3e-form-field>
        </m3e-list-item>
        <m3e-list-item>
          每次休息可用时长
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
          不适部位
          <m3e-chip-set class="chips">
            <m3e-filter-chip v-for="option in bodyPartOptions" :key="option.value" :value="option.value"
              :selected.prop="form.body_parts.includes(option.value)" @change="togglePart(option.value)">
              {{ option.label }}
            </m3e-filter-chip>
          </m3e-chip-set>
        </m3e-list-item>
        <m3e-list-item>
          疼痛程度
          <div class="pain">
            <m3e-slider class="slider" max="10" step="1" @input="onPainChange" @change="onPainChange">
              <m3e-slider-thumb :value.prop="form.pain_score"></m3e-slider-thumb>
            </m3e-slider>
            <div class="scale">
              <span>无痛</span>
              <span class="value mono">{{ form.pain_score }}<small> / 10</small></span>
              <span>无法忍受</span>
            </div>
          </div>
        </m3e-list-item>
        <m3e-list-item>
          <m3e-checkbox :checked.prop="form.acute_discomfort" @change="form.acute_discomfort = $event.target.checked"
            slot="leading"></m3e-checkbox>
          现在就有明显不适
        </m3e-list-item>
      </m3e-list>

      <ErrorBanner :error="state.error" />

      <m3e-button class="primary-action" variant="filled" size="medium" :disabled.prop="state.busy"
        @click="submitAssessment(form)">
        {{ state.busy ? "提交中…" : "生成方案" }}
      </m3e-button>
    </div>
    <LoadingOverlay v-if="state.busy" label="正在生成方案…" />
  </m3e-card>
</template>

<style scoped>
m3e-list.assessForm {
  margin-bottom: 1rem;

  --m3e-form-field-font-size: 1.4rem
}

.field {
  width: 14rem;
  margin-top: 1.4rem;
}

.pain {
  display: block;
  margin-top: 0.75rem;
}

.scale {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  color: var(--md-sys-color-outline);
  font-size: 0.7rem;
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
  margin: 0.75rem 0 0;
  --m3e-slider-min-width: 100%;
  --m3e-slider-tick-size: 0.2rem;
}


.primary-action {
  margin-top: 2rem;
}
</style>
