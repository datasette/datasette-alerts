<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { EditorState } from "prosemirror-state";
  import { EditorView } from "prosemirror-view";
  import { keymap } from "prosemirror-keymap";
  import { history, undo, redo } from "prosemirror-history";
  import {
    baseKeymap,
    chainCommands,
    deleteSelection,
    joinBackward,
    selectNodeBackward,
  } from "prosemirror-commands";
  import { templateSchema } from "./schema";
  import VariableMenu from "./VariableMenu.svelte";

  interface Props {
    value: Record<string, unknown> | null;
    variables: string[];
    onchange: (doc: Record<string, unknown>) => void;
  }

  let { value, variables, onchange }: Props = $props();

  let editorEl: HTMLDivElement;
  let view: EditorView | undefined;

  function createState(doc?: Record<string, unknown> | null): EditorState {
    const config = {
      schema: templateSchema,
      plugins: [
        history(),
        keymap({ "Mod-z": undo, "Mod-y": redo, "Mod-Shift-z": redo }),
        keymap(baseKeymap),
      ],
    };
    if (doc && doc.content) {
      return EditorState.create({
        ...config,
        doc: templateSchema.nodeFromJSON(doc),
      });
    }
    return EditorState.create(config);
  }

  function insertVariable(varName: string) {
    if (!view) return;
    const node = templateSchema.nodes.templateVariable.create({ varName });
    const tr = view.state.tr.replaceSelectionWith(node);
    view.dispatch(tr);
    view.focus();
  }

  onMount(() => {
    const state = createState(value);
    view = new EditorView(editorEl, {
      state,
      dispatchTransaction(tr) {
        const newState = view!.state.apply(tr);
        view!.updateState(newState);
        if (tr.docChanged) {
          onchange(newState.doc.toJSON());
        }
      },
    });
  });

  onDestroy(() => {
    view?.destroy();
  });
</script>

<div class="template-editor-wrapper">
  <VariableMenu {variables} oninsert={insertVariable} />
  <div class="template-editor" bind:this={editorEl}></div>
</div>

<style>
  .template-editor-wrapper {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .template-editor {
    border: 1px solid #ccc;
    border-radius: 4px;
    min-height: 80px;
    padding: 0.4rem 0.5rem;
    font-size: 0.9rem;
  }
  .template-editor :global(.ProseMirror) {
    outline: none;
    min-height: 60px;
  }
  .template-editor :global(.ProseMirror p) {
    margin: 0 0 0.3em 0;
  }
  .template-editor :global(.template-var-pill) {
    display: inline-block;
    padding: 0.1rem 0.4rem;
    border: 1px solid #b3d4fc;
    border-radius: 10px;
    background: #e8f0fe;
    color: #1a56db;
    font-size: 0.8rem;
    font-family: monospace;
    vertical-align: baseline;
    user-select: none;
  }
</style>
