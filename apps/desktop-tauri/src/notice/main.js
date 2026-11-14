import { createApp } from "vue";

import "@m3e/web/all";
import "material-symbols";

import "../assets/theme.css";
import "../assets/font.css";
import "./notice.css";

import { initSystemTheme } from "../theme.js";
import NoticeCard from "./NoticeCard.vue";

initSystemTheme();
createApp(NoticeCard).mount("#notice");
