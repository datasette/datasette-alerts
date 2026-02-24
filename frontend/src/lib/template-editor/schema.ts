import { Schema } from "prosemirror-model";

export const templateSchema = new Schema({
  nodes: {
    doc: { content: "block+" },
    paragraph: {
      content: "inline*",
      group: "block",
      parseDOM: [{ tag: "p" }],
      toDOM() {
        return ["p", 0];
      },
    },
    text: { group: "inline" },
    templateVariable: {
      group: "inline",
      inline: true,
      atom: true,
      attrs: { varName: { default: "" } },
      parseDOM: [
        {
          tag: "span.template-var-pill",
          getAttrs(dom: HTMLElement) {
            return { varName: dom.getAttribute("data-var") || "" };
          },
        },
      ],
      toDOM(node) {
        return [
          "span",
          {
            class: "template-var-pill",
            "data-var": node.attrs.varName,
          },
          `{{${node.attrs.varName}}}`,
        ];
      },
    },
  },
});
