import { h, render } from "preact";
import { useReducer, useState } from "preact/hooks";
import { batch, computed, signal, useSignalEffect } from "@preact/signals";

function main() {
  const root = document.getElementById("root")!;
  render(<div></div>, root);
}
document.addEventListener("DOMContentLoaded", main);