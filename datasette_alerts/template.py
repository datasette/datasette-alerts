def resolve_template(template_doc: dict, variables: dict) -> str:
    """
    Walk a ProseMirror JSON document tree, substituting templateVariable
    nodes with values from `variables`. Returns plain text with paragraphs
    separated by newlines.
    """
    if not template_doc or "content" not in template_doc:
        return ""

    paragraphs = []
    for block in template_doc["content"]:
        if block.get("type") == "paragraph":
            paragraphs.append(_resolve_paragraph(block, variables))
    return "\n".join(paragraphs)


def _resolve_paragraph(node: dict, variables: dict) -> str:
    parts = []
    for child in node.get("content", []):
        node_type = child.get("type")
        if node_type == "text":
            parts.append(child.get("text", ""))
        elif node_type == "templateVariable":
            var_name = child.get("attrs", {}).get("varName", "")
            parts.append(variables.get(var_name, f"{{{{{var_name}}}}}"))
    return "".join(parts)
