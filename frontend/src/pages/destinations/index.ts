import { mount } from "svelte";
import DestinationsPage from "./DestinationsPage.svelte";

const app = mount(DestinationsPage, {
  target: document.getElementById("app-root")!,
});

export default app;
