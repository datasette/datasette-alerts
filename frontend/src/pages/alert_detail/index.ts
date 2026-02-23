import { mount } from "svelte";
import AlertDetailPage from "./AlertDetailPage.svelte";

const app = mount(AlertDetailPage, {
  target: document.getElementById("app-root")!,
});

export default app;
