import json
import os
import re
import sys
import time

from groq import Groq
from groq.types.chat import ChatCompletion

try:
    from .prompts import SYSTEM_PROMPT, TOOLS
    from .sandbox import execute_python
except ImportError:
    from prompts import SYSTEM_PROMPT, TOOLS
    from sandbox import execute_python

# Ensure console supports UTF-8 on Windows
_reconfigure = getattr(sys.stdout, "reconfigure", None)
if callable(_reconfigure):
    try:
        _reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


DEFAULT_MODELS = [
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]


def _extract_tool_call_from_text(text: str) -> tuple[str | None, dict]:
    """
    Extracts function name and argument dict from raw/failed LLM generation text
    such as `<tool_call><function=final_answer><parameter=text>...`.
    """
    if not text:
        return None, {}

    # Check for <function=NAME> and <parameter=PARAM>...</tool_call> or EOF
    fn_match = re.search(r"<function=([a-zA-Z0-9_]+)>", text)
    if fn_match:
        fn_name = fn_match.group(1)
        param_match = re.search(
            r"<parameter=([a-zA-Z0-9_]+)>\s*([\s\S]*?)(?:</tool_call>|</function>|$)",
            text,
        )
        if param_match:
            p_name = param_match.group(1)
            p_val = param_match.group(2).strip()
            return fn_name, {p_name: p_val}
        # If no explicit parameter tag, treat remaining text as parameter
        after_fn = text[fn_match.end() :].strip()
        after_fn = re.sub(r"</?tool_call>", "", after_fn).strip()
        key = "text" if fn_name == "final_answer" else "code"
        return fn_name, {key: after_fn}

    # Check for JSON block within text
    json_match = re.search(r'\{[\s\S]*"name"\s*:\s*"([a-zA-Z0-9_]+)"[\s\S]*\}', text)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            fn_name = parsed.get("name")
            args = parsed.get("arguments", parsed.get("parameters", {}))
            if isinstance(args, str):
                args = json.loads(args)
            return fn_name, args
        except Exception:
            pass

    return None, {}


def _extract_code_from_raw_args(raw_args: str) -> str:
    """Extracts python code from raw arguments even if JSON decoding fails or is truncated."""
    if not raw_args or not isinstance(raw_args, str):
        return ""
    raw = raw_args.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            c = parsed.get("code") or parsed.get("python") or ""
            if c:
                return c
        elif isinstance(parsed, str):
            return parsed
    except Exception:
        pass

    # Markdown fenced block
    md_match = re.search(r"```(?:python)?\s*([\s\S]*?)\s*```", raw)
    if md_match:
        return md_match.group(1).strip()

    # JSON-like "code": "..."
    code_match = re.search(r'"code"\s*:\s*"([\s\S]*)$', raw)
    if code_match:
        val = code_match.group(1)
        val = re.sub(r'"\s*\}?\s*$', "", val)
        try:
            val = json.loads(f'"{val}"')
        except Exception:
            val = (
                val.replace("\\n", "\n")
                .replace('\\"', '"')
                .replace("\\t", "\t")
                .replace("\\\\", "\\")
            )
        return val.strip()

    return raw


def _clean_final_text(text: str | None) -> str:
    """
    Strips <think> tags or raw tool XML artifacts if present in LLM outputs,
    and ensures proper Markdown formatting so tabular records and key metrics
    never collapse into a single run-on paragraph.
    """
    if not text:
        return ""
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    if "<function=final_answer>" in cleaned:
        match = re.search(r"<parameter=[^>]+>\s*([\s\S]*?)(?:</tool_call>|</function>|$)", cleaned)
        if match and match.group(1).strip():
            cleaned = match.group(1).strip()
    # Strip any remaining tool tags if present
    cleaned = re.sub(r"</?(?:tool_call|function(?:=[^>]+)?|parameter(?:=[^>]+)?)>", "", cleaned).strip()

    # Post-process lines outside fenced code blocks to prevent Markdown newline collapsing
    parts = re.split(r"(```[\s\S]*?```)", cleaned)
    formatted_parts = []
    for part in parts:
        if part.startswith("```"):
            formatted_parts.append(part)
            continue

        lines = part.split("\n")
        new_lines = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                new_lines.append("")
                continue

            # If line is already a markdown heading, list item, table row, blockquote, or horizontal rule
            if stripped.startswith(("#", "-", "*", ">", "|", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "---", "___")):
                new_lines.append(line)
                continue

            # If line is followed by another non-empty line that isn't a heading, table row, or list item,
            # ensure it has 2 trailing spaces so Markdown treats it as a hard line break instead of collapsing it
            if i + 1 < len(lines):
                next_stripped = lines[i + 1].strip()
                if next_stripped and not next_stripped.startswith(("#", "```", "---", "___")):
                    new_lines.append(line.rstrip() + "  ")
                    continue

            new_lines.append(line)

        formatted_parts.append("\n".join(new_lines))

    return "".join(formatted_parts).strip()


def _is_valid_executive_report(text: str | None) -> bool:
    """Validates that a generated response is an actual answer/report rather than intermediate chatter or raw code."""
    if not text or not text.strip():
        return False
    t = text.strip()
    if t.startswith("import ") or "<tool_call>" in t or "<function=" in t:
        return False
    if t.startswith("```python") and t.endswith("```") and len(t.splitlines()) < 8:
        return False
    lower = t.lower()
    chatter_starts = (
        "let me execute",
        "i need to run",
        "let me run",
        "i will run",
        "let's execute",
        "executing python",
        "i will execute",
        "i will calculate",
        "i will write",
    )
    if any(lower.startswith(cue) for cue in chatter_starts) and len(t.split()) < 25:
        return False
    if len(t.split()) < 3:
        return False
    return True


def _prune_past_history(history: list) -> list:
    """
    Prunes verbose raw tool outputs and intermediate execution logs from completed
    earlier turns to prevent TPM/rate-limit exhaustion, while preserving the system
    dataset profile and high-level conversational context.
    """
    if not history:
        return []

    system_msg = history[0]
    pruned = [system_msg]

    prev_messages = history[1:]
    for msg in prev_messages:
        role = msg.get("role")
        if role == "user":
            content = str(msg.get("content", ""))
            # Exclude intermediate tool execution feedback prompts from previous turns
            if not content.startswith("Tool execution result:") and not content.startswith("Result:"):
                pruned.append({"role": "user", "content": content})
        elif role == "assistant":
            # Keep final responses, ignore intermediate code execution snippets
            content = msg.get("content")
            if content and not content.startswith("```python"):
                pruned.append({"role": "assistant", "content": _clean_final_text(str(content))})

    # Keep at most system prompt + last 3 Q&A pairs (6 messages)
    if len(pruned) > 7:
        pruned = [pruned[0]] + pruned[-6:]

    return pruned


def _safe_serialize_profile(profile_dict: dict) -> str:
    """Safely serialize profile dictionary to JSON string without circular reference errors."""
    if not profile_dict:
        return "{}"
    try:
        return json.dumps(profile_dict, separators=(",", ":"), default=str)
    except Exception:
        # Decycle in case of any recursive references in cached objects
        def _decycle(obj, seen=None):
            if seen is None:
                seen = set()
            obj_id = id(obj)
            if obj_id in seen:
                return "<reference>"
            seen.add(obj_id)
            if isinstance(obj, dict):
                return {str(k): _decycle(v, seen.copy()) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_decycle(item, seen.copy()) for item in obj]
            return obj

        safe_dict = _decycle(profile_dict)
        return json.dumps(safe_dict, separators=(",", ":"), default=str)


class CSVInsightAgent:
    """Agent that uses Groq LLM with tool-calling to analyze CSV data."""

    def __init__(self, model_name: str = "qwen/qwen3.8-27b"):
        api_key = os.getenv("GROQ_API_KEY")
        # Fallback: read from Streamlit secrets (for Streamlit Cloud deployment)
        if not api_key:
            try:
                import streamlit as st
                api_key = st.secrets.get("GROQ_API_KEY")
            except Exception:
                pass
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in environment, .env file, or Streamlit secrets.")

        self.client = Groq(api_key=api_key)
        self.model_name = model_name

    def run_turn(
        self,
        user_question: str,
        profile_dict: dict,
        namespace: dict,
        history: list | None = None,
        max_turns: int = 6,
        status_callback: object = None,
        cancel_event: object = None,
    ) -> dict:
        """
        Run one agent turn for a user question.

        Parameters:
          user_question — user prompt or automated instruction
          profile_dict  — dataset profile generated by profiler.py
          namespace     — persistent session namespace containing `df`
          history       — list of previous messages in session
          max_turns     — limit on tool execution loops to avoid infinite loops

        Returns dict:
          {
            "answer": str,           # Plain-English answer from final_answer tool
            "charts": list[bytes],   # List of matplotlib PNG bytes produced during turn
            "history": list,         # Updated conversation history
            "executed_code": list,   # Code snippets executed during turn
          }
        """
        if history is None:
            history = []

        # Build initial system message or prune past turns
        if not history:
            profile_str = _safe_serialize_profile(profile_dict)
            target_label = "the loaded datasets ('dfs')" if profile_dict.get("is_multi_dataset") else "the loaded DataFrame 'df'"
            initial_system_content = f"{SYSTEM_PROMPT}\n\nHere is the factual profile of {target_label}:\n```json\n{profile_str}\n```"
            history = [{"role": "system", "content": initial_system_content}]
        else:
            history = _prune_past_history(history)

        # Append user question to history
        history.append({"role": "user", "content": user_question})

        charts = []
        executed_code = []
        final_text = None

        turn_count = 0
        while turn_count < max_turns:
            if cancel_event and getattr(cancel_event, "is_set", lambda: False)():
                break

            turn_count += 1

            response = None
            candidate_models = [self.model_name] + [
                m for m in DEFAULT_MODELS if m != self.model_name
            ]
            last_err = None

            # Always use "auto" to prevent Groq 400 Bad Request on named function forcing
            current_tool_choice = "auto"

            for cand_model in candidate_models:
                try:
                    if status_callback and callable(status_callback):
                        try:
                            phase = "synthesis" if executed_code else "planning"
                            is_retry = (cand_model != candidate_models[0])
                            status_callback(
                                "model_calling",
                                {
                                    "step": turn_count,
                                    "model": cand_model,
                                    "phase": phase,
                                    "is_retry": is_retry,
                                },
                            )
                        except Exception:
                            pass

                    call_kwargs = {}
                    if "qwen" in cand_model.lower():
                        call_kwargs["reasoning_effort"] = "none"
                        call_kwargs["max_tokens"] = 4096
                    else:
                        call_kwargs["max_tokens"] = 4096

                    response = self.client.chat.completions.create(
                        model=cand_model,
                        messages=history,
                        tools=TOOLS,
                        tool_choice=current_tool_choice,
                        temperature=0.2,
                        stream=False,
                        **call_kwargs,
                    )
                    self.model_name = cand_model
                    break
                except Exception as e:
                    last_err = e
                    err_str = str(e)

                    # Check if error contains failed_generation that can be recovered
                    failed_gen = None
                    error_body = getattr(e, "body", None)
                    if isinstance(error_body, dict):
                        failed_gen = error_body.get("error", {}).get("failed_generation")
                    if not failed_gen:
                        match = re.search(
                            r"'failed_generation':\s*['\"]([\s\S]*?)['\"]\s*\}", err_str
                        )
                        if match:
                            failed_gen = match.group(1)

                    if failed_gen:
                        extracted_fn, extracted_args = _extract_tool_call_from_text(
                            failed_gen
                        )
                        if extracted_fn == "final_answer":
                            candidate_ans = _clean_final_text(extracted_args.get("text", failed_gen))
                            if _is_valid_executive_report(candidate_ans):
                                final_text = candidate_ans
                                break
                        elif extracted_fn == "execute_python":
                            code = extracted_args.get("code", "")
                            if code:
                                executed_code.append(code)
                                if status_callback and callable(status_callback):
                                    try:
                                        status_callback("code_generated", {"step": turn_count, "code": code})
                                        status_callback("code_executing", {"step": turn_count, "code": code})
                                    except Exception:
                                        pass
                                exec_result = execute_python(code, namespace)
                                new_charts = exec_result.get("all_charts") or []
                                if not new_charts:
                                    item = exec_result.get("plotly_fig") or exec_result.get("chart_png")
                                    if item is not None:
                                        new_charts = [item]
                                for ch in new_charts:
                                    if ch not in charts:
                                        charts.append(ch)
                                if status_callback and callable(status_callback):
                                    try:
                                        status_callback(
                                            "code_executed",
                                            {
                                                "step": turn_count,
                                                "stdout": exec_result.get("stdout"),
                                                "has_chart": bool(exec_result.get("has_chart")),
                                                "is_plotly": bool(exec_result.get("plotly_fig") is not None),
                                                "success": exec_result.get("success"),
                                                "error": exec_result.get("error"),
                                            },
                                        )
                                    except Exception:
                                        pass

                                history.append(
                                    {
                                        "role": "assistant",
                                        "content": f"```python\n{code}\n```",
                                    }
                                )
                                stdout_str = (
                                    exec_result["stdout"]
                                    or "Code executed successfully."
                                )
                                if exec_result.get("plotly_fig") is not None:
                                    chart_msg = "\n(Note: Interactive Plotly chart was successfully generated and captured.)"
                                elif exec_result.get("chart_png"):
                                    chart_msg = "\n(Note: Chart was successfully generated and captured.)"
                                else:
                                    chart_msg = ""
                                history.append(
                                    {
                                        "role": "user",
                                        "content": f"Tool execution result:\n{stdout_str}{chart_msg}\nIf calculations and charts are complete, call 'final_answer' now with your full report; otherwise call 'execute_python' to continue analysis.",
                                    }
                                )
                                response = None
                                break

                    # If model parse failed but we already have executed code, synthesize directly
                    if (
                        "output_parse_failed" in err_str or "tool_use_failed" in err_str
                    ) and executed_code:
                        try:
                            synth_kwargs = {}
                            if "qwen" in cand_model.lower():
                                synth_kwargs["reasoning_effort"] = "none"
                                synth_kwargs["max_tokens"] = 4096
                            else:
                                synth_kwargs["max_tokens"] = 4096
                            synthesis = self.client.chat.completions.create(
                                model=cand_model,
                                messages=history
                                + [
                                    {
                                        "role": "user",
                                        "content": "Please synthesize all the computed results into the complete 5-section executive markdown report now.",
                                    }
                                ],
                                temperature=0.2,
                                stream=False,
                                **synth_kwargs,
                            )
                            if (
                                isinstance(synthesis, ChatCompletion)
                                and synthesis.choices
                                and synthesis.choices[0].message.content
                            ):
                                candidate_ans = _clean_final_text(
                                    synthesis.choices[0].message.content
                                )
                                if _is_valid_executive_report(candidate_ans):
                                    final_text = candidate_ans
                                    break
                        except Exception:
                            pass

                    if (
                        "429" in err_str
                        or "rate_limit" in err_str.lower()
                        or "400" in err_str
                    ):
                        time.sleep(0.5)
                        continue

            if final_text and _is_valid_executive_report(final_text):
                break

            if not isinstance(response, ChatCompletion) or not response.choices:
                if last_err is not None and not final_text and executed_code:
                    # Fallback direct generation without tools
                    try:
                        fallback_kwargs = {}
                        if "qwen" in self.model_name.lower():
                            fallback_kwargs["reasoning_effort"] = "none"
                            fallback_kwargs["max_tokens"] = 4096
                        else:
                            fallback_kwargs["max_tokens"] = 4096
                        fallback_resp = self.client.chat.completions.create(
                            model=self.model_name,
                            messages=history
                            + [
                                {
                                    "role": "user",
                                    "content": "Deliver the complete 5-section executive report based on the data findings now.",
                                }
                            ],
                            temperature=0.2,
                            stream=False,
                            **fallback_kwargs,
                        )
                        if (
                            isinstance(fallback_resp, ChatCompletion)
                            and fallback_resp.choices
                            and fallback_resp.choices[0].message.content
                        ):
                            candidate_ans = _clean_final_text(
                                fallback_resp.choices[0].message.content
                            )
                            if _is_valid_executive_report(candidate_ans):
                                final_text = candidate_ans
                                break
                    except Exception:
                        pass
                if not isinstance(response, ChatCompletion) or not response.choices:
                    continue

            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            # Convert message to dict format for history
            msg_dict: dict[str, object] = {"role": "assistant"}
            if response_message.content:
                msg_dict["content"] = response_message.content
            if tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]

            history.append(msg_dict)

            # If LLM didn't call any tools, check if text content is available as the final answer
            if not tool_calls:
                if response_message.content and response_message.content.strip():
                    content_str = response_message.content.strip()
                    # Check if model outputted XML tool call in content
                    if "<tool_call>" in content_str or "<function=" in content_str:
                        extracted_fn, extracted_args = _extract_tool_call_from_text(
                            content_str
                        )
                        if extracted_fn == "final_answer":
                            raw_answer = extracted_args.get("text", content_str)
                            candidate_ans = _clean_final_text(str(raw_answer) if raw_answer else content_str)
                            if _is_valid_executive_report(candidate_ans):
                                final_text = candidate_ans
                                break
                        elif extracted_fn == "execute_python":
                            code = extracted_args.get("code", "")
                            if code:
                                executed_code.append(code)
                                if status_callback and callable(status_callback):
                                    try:
                                        status_callback("code_generated", {"step": turn_count, "code": code})
                                        status_callback("code_executing", {"step": turn_count, "code": code})
                                    except Exception:
                                        pass
                                exec_result = execute_python(code, namespace)
                                new_charts = exec_result.get("all_charts") or []
                                if not new_charts:
                                    item = exec_result.get("plotly_fig") or exec_result.get("chart_png")
                                    if item is not None:
                                        new_charts = [item]
                                for ch in new_charts:
                                    if ch not in charts:
                                        charts.append(ch)
                                if status_callback and callable(status_callback):
                                    try:
                                        status_callback(
                                            "code_executed",
                                            {
                                                "step": turn_count,
                                                "stdout": exec_result.get("stdout"),
                                                "has_chart": bool(exec_result.get("has_chart")),
                                                "is_plotly": bool(exec_result.get("plotly_fig") is not None),
                                                "success": exec_result.get("success"),
                                                "error": exec_result.get("error"),
                                            },
                                        )
                                    except Exception:
                                        pass
                                stdout_str = (
                                    exec_result["stdout"] or "Executed successfully."
                                )
                                history.append(
                                    {
                                        "role": "user",
                                        "content": f"Result:\n{stdout_str}\nPlease finalize your complete 5-section executive report now.",
                                    }
                                )
                                continue

                    cleaned = _clean_final_text(content_str)
                    if _is_valid_executive_report(cleaned):
                        final_text = cleaned
                        break
                    else:
                        # LLM outputted conversational chatter/promise instead of report
                        history.append(
                            {
                                "role": "user",
                                "content": "Please synthesize the computed results and deliver your complete 5-section executive report now. Do not output conversational promises.",
                            }
                        )
                        continue
                else:
                    # Prompt the LLM to synthesize the final answer
                    history.append(
                        {
                            "role": "user",
                            "content": "Please synthesize all your findings and deliver the comprehensive 5-section executive report now.",
                        }
                    )
                    continue

            # Handle Tool Calls
            tool_finished = False
            for tool_call in tool_calls:
                func_name = tool_call.function.name
                raw_args = tool_call.function.arguments or ""

                try:
                    arguments = json.loads(raw_args)
                    if isinstance(arguments, str):
                        arguments = {"text": arguments, "code": arguments}
                except Exception:
                    # Robust fallback parsing if JSON decode fails
                    extracted_code = _extract_code_from_raw_args(raw_args)
                    arguments = {"text": raw_args, "code": extracted_code}

                if func_name == "final_answer":
                    answer_text = (
                        arguments.get("text") or arguments.get("answer") or raw_args
                    )
                    candidate_ans = _clean_final_text(str(answer_text))
                    if _is_valid_executive_report(candidate_ans):
                        final_text = candidate_ans
                        tool_finished = True
                        history.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": "Final answer recorded successfully.",
                            }
                        )
                        break
                    else:
                        history.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": "The answer provided is too brief or incomplete. Please deliver the full 5-section executive report with empirical findings.",
                            }
                        )
                        continue

                elif func_name == "execute_python":
                    code = arguments.get("code") or arguments.get("python") or raw_args
                    executed_code.append(code)

                    if status_callback and callable(status_callback):
                        try:
                            status_callback("code_generated", {"step": turn_count, "code": code})
                            status_callback("code_executing", {"step": turn_count, "code": code})
                        except Exception:
                            pass

                    # Execute in sandbox
                    exec_result = execute_python(code, namespace)

                    # Store all charts if created (Plotly and/or Matplotlib)
                    new_charts = exec_result.get("all_charts") or []
                    if not new_charts:
                        item = exec_result.get("plotly_fig") or exec_result.get("chart_png")
                        if item is not None:
                            new_charts = [item]
                    for ch in new_charts:
                        if ch not in charts:
                            charts.append(ch)

                    if status_callback and callable(status_callback):
                        try:
                            status_callback(
                                "code_executed",
                                {
                                    "step": turn_count,
                                    "stdout": exec_result.get("stdout"),
                                    "has_chart": bool(exec_result.get("has_chart")),
                                    "is_plotly": bool(exec_result.get("plotly_fig") is not None),
                                    "success": exec_result.get("success"),
                                    "error": exec_result.get("error"),
                                },
                            )
                        except Exception:
                            pass

                    # Format output for LLM
                    if exec_result["success"]:
                        stdout_str = (
                            exec_result["stdout"]
                            or "Code executed successfully with no print output."
                        )
                        if exec_result.get("plotly_fig") is not None:
                            chart_msg = "\n(Note: An interactive Plotly visualization was successfully generated and captured.)"
                        elif exec_result.get("chart_png"):
                            chart_msg = "\n(Note: A matplotlib chart was successfully generated and captured.)"
                        else:
                            chart_msg = ""
                        tool_output_content = (
                            f"EXECUTION SUCCESSFUL:\n{stdout_str}{chart_msg}\n\n"
                            "If your computed results and visualizations fully answer the user's question, call 'final_answer' now with your complete executive report. "
                            "If you still need additional data, calculations, or an interactive Plotly chart to fully answer the inquiry, call 'execute_python' again."
                        )
                    else:
                        tool_output_content = f"EXECUTION FAILED:\n{exec_result['error']}\nPlease analyze the error and fix your code."

                    # Append tool response to message history
                    history.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_output_content,
                        }
                    )

            if tool_finished and final_text and _is_valid_executive_report(final_text):
                break

        # Keep tool output available for the final fallback even when synthesis is skipped.
        collected_outputs = []

        is_cancelled = bool(cancel_event and getattr(cancel_event, "is_set", lambda: False)())

        # If the turn loop completed without producing a valid executive report, perform an explicit synthesis call
        if not is_cancelled and not _is_valid_executive_report(final_text):
            if status_callback and callable(status_callback):
                try:
                    status_callback(
                        "synthesis_start",
                        {"step": turn_count, "code_count": len(executed_code)},
                    )
                except Exception:
                    pass

            # Gather all tool outputs and executed code from history
            for msg in history:
                if msg.get("role") == "tool" and msg.get("content"):
                    raw_c = str(msg.get("content", ""))
                    clean_c = re.sub(r"EXECUTION SUCCESSFUL:\s*", "", raw_c).strip()
                    clean_c = re.sub(r"\(Note:.*?\)", "", clean_c).strip()
                    clean_c = re.sub(r"All required data and visualizations.*", "", clean_c).strip()
                    clean_c = re.sub(r"If your computed results.*", "", clean_c).strip()
                    clean_c = re.sub(r"Call 'final_answer'.*", "", clean_c).strip()
                    if clean_c:
                        collected_outputs.append(clean_c)

            data_context = "\n\n".join(collected_outputs).strip()
            if not data_context:
                data_context = "Analysis code was executed against the dataset."

            synthesis_prompt = (
                f"You are an executive data scientist and business advisor.\n\n"
                f"The user asked the following question about the dataset:\n\"{user_question}\"\n\n"
                f"Here are the empirical calculations and outputs produced by the Python analysis:\n"
                f"```\n{data_context}\n```\n\n"
                "Deliver a comprehensive, plain-English executive intelligence briefing answering the user's question directly. "
                "Highlight the key numbers, rankings, percentages, and strategic insights. "
                "Structure your response with clear markdown headings, bullet points, and an executive summary. "
                "CRITICAL FORMATTING RULES:\n"
                "- NEVER dump raw space-separated terminal or dataframe text, as Markdown collapses single newlines into a continuous paragraph.\n"
                "- ALWAYS format lists of items, entities, rankings, or students as a clean Markdown table (| Col 1 | Col 2 |) with clear headers or as a bulleted list with bold names.\n"
                "- Round all floating-point numbers cleanly (e.g., 68.4 mins, 2.17%).\n"
                "- If there are many records (>15), state the total count, highlight key patterns, and present the top 10-15 rows in a clean Markdown table.\n"
                "Do NOT output python code, XML tool tags, or conversational promises; output your complete answer now."
            )

            candidate_models = [self.model_name] + [
                m for m in DEFAULT_MODELS if m != self.model_name
            ]
            for cand_model in candidate_models:
                try:
                    synth_kwargs = {}
                    if "qwen" in cand_model.lower():
                        synth_kwargs["reasoning_effort"] = "none"
                        synth_kwargs["max_tokens"] = 4096
                    else:
                        synth_kwargs["max_tokens"] = 4096

                    synthesis_resp = self.client.chat.completions.create(
                        model=cand_model,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a Lead Data Science Advisor. Always deliver a thorough, structured, empirical plain-English answer in markdown.",
                            },
                            {"role": "user", "content": synthesis_prompt},
                        ],
                        temperature=0.2,
                        stream=False,
                        **synth_kwargs,
                    )
                    if (
                        isinstance(synthesis_resp, ChatCompletion)
                        and synthesis_resp.choices
                    ):
                        content = synthesis_resp.choices[0].message.content
                        if content and content.strip():
                            cleaned = _clean_final_text(content)
                            if _is_valid_executive_report(cleaned):
                                final_text = cleaned
                                self.model_name = cand_model
                                break
                except Exception:
                    continue

        if is_cancelled:
            return {
                "answer": "Analysis was stopped by user.",
                "charts": charts,
                "history": history,
                "executed_code": executed_code,
            }

        if not final_text or not final_text.strip():
            # Robust formatted fallback when API is unreachable
            if collected_outputs:
                clean_lines = "\n".join([f"- {line}" for line in collected_outputs[-1].splitlines() if line.strip() and not line.startswith("<Arrow")])
                final_text = (
                    f"### Findings for: {user_question}\n\n"
                    f"The dataset was analyzed and produced the following empirical results:\n\n"
                    f"{clean_lines if clean_lines else collected_outputs[-1]}\n\n"
                    f"Review the generated visualizations and metrics above for complete details."
                )
            elif charts:
                final_text = f"### Analysis for: {user_question}\n\nAnalysis completed with computed findings and visualizations. Review the visual breakdown above."
            else:
                final_text = f"### Analysis for: {user_question}\n\nAnalysis completed. Review the executed Python code steps above for details."

        final_text = _clean_final_text(final_text)

        if status_callback and callable(status_callback):
            try:
                status_callback(
                    "completed",
                    {"has_answer": bool(final_text), "charts_count": len(charts)},
                )
            except Exception:
                pass

        return {
            "answer": final_text,
            "charts": charts,
            "history": history,
            "executed_code": executed_code,
        }
