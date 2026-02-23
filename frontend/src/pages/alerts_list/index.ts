import { mount } from "svelte";
import AlertsListPage from "./AlertsListPage.svelte";

const app = mount(AlertsListPage, {
  target: document.getElementById("app-root")!,
});

export default app;
