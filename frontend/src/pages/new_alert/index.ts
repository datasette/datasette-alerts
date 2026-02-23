import { mount } from "svelte";
import NewAlertPage from "./NewAlertPage.svelte";

const app = mount(NewAlertPage, {
  target: document.getElementById("app-root")!,
});

export default app;
