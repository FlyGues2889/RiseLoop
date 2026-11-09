import { createApp } from "vue";
import App from "./App.vue";

import "@m3e/web/all";
import 'material-symbols';

import "./assets/theme.css";
import "./assets/styles.css";
import "./assets/font.css";

import { initSystemTheme } from "./theme.js";

initSystemTheme();
createApp(App).mount("#app");
