# Code sanitizer and syntax repair tools
import json
import re


# Clean and fix Python code snippets before execution
def sanitize_and_repair_code(code: str) -> str:
    if not code or not isinstance(code, str):
        return ""

    code = code.strip()

    if code.startswith("```python"):
        code = code[len("```python") :].strip()
    elif code.startswith("```"):
        code = code[3:].strip()
    if code.endswith("```"):
        code = code[:-3].strip()

    if code.startswith('{"code"') or code.startswith("{\n  \"code\"") or '"code":' in code[:30]:
        try:
            parsed = json.loads(code)
            if isinstance(parsed, dict) and "code" in parsed:
                code = parsed["code"]
        except Exception:
            match = re.search(r'"code"\s*:\s*"([\s\S]*)$', code)
            if match:
                val = match.group(1)
                val = re.sub(r'"\s*\}?\s*$', "", val)
                val = (
                    val.replace("\\n", "\n")
                    .replace('\\"', '"')
                    .replace("\\t", "\t")
                    .replace("\\\\", "\\")
                )
                code = val.strip()

    lines = code.splitlines()
    for _ in range(5):
        try:
            compile("\n".join(lines), "<string>", "exec")
            return "\n".join(lines)
        except SyntaxError as e:
            err_msg = str(e)
            if (
                "unterminated string literal" in err_msg
                or "unexpected EOF" in err_msg
                or "EOF while scanning" in err_msg
            ):
                if lines:
                    lines.pop()
                else:
                    break
            else:
                break

    return code
