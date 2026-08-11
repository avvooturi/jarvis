import re


TOOL_PATTERNS = (
    r'\b(open|launch|start|close|quit|create|delete|remove|rename|move|copy)\b',
    r'\b(file|folder|project|application|app|browser|website|device)\b',
    r'\b(run|execute|install|download|upload|send|email|schedule)\b',
)


def needs_tools(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in TOOL_PATTERNS)
