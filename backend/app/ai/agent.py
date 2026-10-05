"""智能预约 Agent：ReAct 循环（思考 → 调用工具 → 观察 → 回答）+ SSE 事件流。

无论底层是否有大模型，对外都产出同一种事件协议：
  start / thought / tool_call / tool_result / delta / done / error
前端据此实现"过程可见"的打字机效果。
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.ai import llm, local_engine, rag
from app.ai import tools as T
from app.models import ChatMessage, ChatSession, User

logger = logging.getLogger("lab-booking.agent")

MAX_STEPS = 5

SYSTEM_PROMPT = """你是「智能实验室预约系统」的 AI 助手，服务于高校实验室管理平台。

今天是 {today}（{weekday}），当前用户：{user_name}（{role}）。

你的职责：
1. 帮学生查询实验室的位置、容量、开放时间、状态与设备清单；
2. 查询某实验室某天的空闲时段；
3. 帮用户提交实验室预约申请（提交后为「待审核」，需管理员审核）；
4. 查询用户的预约记录与审核结果；
5. 解答实验室规章制度、安全须知、设备操作规范等问题。

工作要求：
- 必须调用工具获取真实数据，禁止编造实验室名称、时间或设备信息。
- 提交预约前必须确认：实验室、日期、开始时间、结束时间；信息不全时先向用户追问。
- 若工具返回冲突或校验失败，如实说明原因并给出可选时段建议。
- 用简体中文回答，条理清晰，善用 Markdown 列表与加粗；不要输出 JSON 原文。
- 涉及安全与违规操作（如超时占用、私自改装设备）要明确提醒遵守规定。"""


def _today_info() -> tuple[str, str]:
    today = dt.date.today()
    return today.isoformat(), T.WEEKDAY_CN[today.weekday()]


def build_system_prompt(user: User, rag_context: list[dict]) -> str:
    today, weekday = _today_info()
    prompt = SYSTEM_PROMPT.format(
        today=today, weekday=weekday, user_name=user.name or user.username,
        role=user.role_text,
    )
    if rag_context:
        blocks = []
        for i, hit in enumerate(rag_context, 1):
            blocks.append(f"[知识{i}] {hit['title']}（{hit['category']}）\n{hit['content']}")
        prompt += "\n\n以下是知识库检索到的参考资料，回答制度类问题时应优先依据它们：\n" + "\n\n".join(blocks)
    return prompt


def _history_messages(db: Session, session_id: int | None, limit: int = 8) -> list[dict]:
    if not session_id:
        return []
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id, ChatMessage.role.in_(("user", "assistant")))
        .order_by(ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


def get_or_create_session(db: Session, user: User, session_id: int | None, first_message: str) -> ChatSession:
    if session_id:
        session = db.get(ChatSession, session_id)
        if session and session.user_id == user.id:
            return session
    title = (first_message or "新的对话").strip()[:20] or "新的对话"
    session = ChatSession(user_id=user.id, title=title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def save_message(db: Session, session_id: int, role: str, content: str,
                 tool_name: str | None = None, tool_args: dict | None = None,
                 tool_result: dict | None = None) -> ChatMessage:
    msg = ChatMessage(
        session_id=session_id,
        role=role,
        content=content or "",
        tool_name=tool_name,
        tool_args=json.dumps(tool_args, ensure_ascii=False) if tool_args else None,
        tool_result=json.dumps(tool_result, ensure_ascii=False)[:4000] if tool_result else None,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


# --------------------------------------------------------------------- Agent
def run(
    db: Session, user: User, message: str, session_id: int | None = None,
    use_rag: bool = True, use_tools: bool = True,
) -> dict:
    """非流式执行，返回完整回答与过程步骤。"""
    session = get_or_create_session(db, user, session_id, message)
    save_message(db, session.id, "user", message)

    rag_context = rag.search(db, message) if use_rag else []
    steps: list[dict] = []

    if not llm.is_enabled() or not use_tools:
        reply, events = local_engine.answer(db, user, message)
        for ev in events:
            steps.append(ev)
            if ev.get("type") == "tool_call":
                save_message(db, session.id, "tool", "", tool_name=ev.get("tool"), tool_args=ev.get("args"))
        save_message(db, session.id, "assistant", reply)
        return {
            "session_id": session.id,
            "reply": reply,
            "steps": steps,
            "mode": "local",
            "rag": rag_context,
        }

    messages = [{"role": "system", "content": build_system_prompt(user, rag_context)}]
    messages += _history_messages(db, session.id)[:-1]
    messages.append({"role": "user", "content": message})

    reply = ""
    used_tools: list[str] = []
    try:
        for _ in range(MAX_STEPS):
            result = llm.chat(messages, tools=T.TOOL_SPECS if use_tools else None)
            steps.append({"type": "thought", "content": result.get("content") or "正在规划…"})
            if not result["tool_calls"]:
                reply = result["content"]
                break
            messages.append(
                {
                    "role": "assistant",
                    "content": result.get("content") or "",
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"], ensure_ascii=False)},
                        }
                        for tc in result["tool_calls"]
                    ],
                }
            )
            for tc in result["tool_calls"]:
                used_tools.append(tc["name"])
                steps.append({"type": "tool_call", "tool": tc["name"], "args": tc["arguments"]})
                output = T.execute_tool(tc["name"], tc["arguments"], db, user)
                steps.append({"type": "tool_result", "tool": tc["name"], "result": output})
                save_message(db, session.id, "tool", "", tool_name=tc["name"],
                             tool_args=tc["arguments"], tool_result=output)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(output, ensure_ascii=False)[:6000],
                    }
                )
        if not reply:
            final = llm.chat(messages)
            reply = final.get("content") or "抱歉，我暂时无法完成这个请求，请换个说法再试。"
    except llm.LLMNotConfigured:
        reply, events = local_engine.answer(db, user, message)
        steps.extend(events)
        return {"session_id": session.id, "reply": reply, "steps": steps, "mode": "local", "rag": rag_context}
    except Exception as exc:  # noqa: BLE001  模型异常时退回本地引擎，保证服务可用
        logger.exception("Agent 执行失败，退回本地引擎")
        steps.append({"type": "error", "content": f"模型调用异常：{exc}，已切换本地引擎"})
        reply, events = local_engine.answer(db, user, message)
        steps.extend(events)
        save_message(db, session.id, "assistant", reply)
        return {"session_id": session.id, "reply": reply, "steps": steps, "mode": "local-fallback", "rag": rag_context}

    save_message(db, session.id, "assistant", reply)
    return {
        "session_id": session.id,
        "reply": reply,
        "steps": steps,
        "mode": "llm",
        "tools_used": used_tools,
        "rag": rag_context,
    }


def stream(
    db: Session, user: User, message: str, session_id: int | None = None,
    use_rag: bool = True, use_tools: bool = True,
) -> Iterator[dict]:
    """SSE 流式执行：先暴露工具的推理过程，再流式输出最终回答。"""
    session = get_or_create_session(db, user, session_id, message)
    save_message(db, session.id, "user", message)
    yield {"type": "start", "session_id": session.id, "title": session.title}

    rag_context = rag.search(db, message) if use_rag else []

    # 未配置模型或关闭工具：走本地引擎
    if not llm.is_enabled() or not use_tools:
        yield {"type": "mode", "mode": "local"}
        try:
            reply, events = local_engine.answer(db, user, message)
        except Exception as exc:  # noqa: BLE001
            yield {"type": "error", "content": f"本地引擎执行失败：{exc}"}
            return
        for ev in events:
            if ev.get("type") == "tool_call":
                save_message(db, session.id, "tool", "", tool_name=ev.get("tool"), tool_args=ev.get("args"))
            yield ev
        for piece in _chunks(reply):
            yield {"type": "delta", "content": piece}
        save_message(db, session.id, "assistant", reply)
        yield {"type": "done", "content": reply, "session_id": session.id}
        return

    yield {"type": "mode", "mode": "llm"}
    if rag_context:
        yield {
            "type": "thought",
            "content": "已检索知识库：" + "、".join(h["title"] for h in rag_context),
        }

    messages = [{"role": "system", "content": build_system_prompt(user, rag_context)}]
    messages += _history_messages(db, session.id)[:-1]
    messages.append({"role": "user", "content": message})

    reply = ""
    try:
        for _ in range(MAX_STEPS):
            yield {"type": "thought", "content": "正在分析问题并规划调用哪些工具…"}
            result = llm.chat(messages, tools=T.TOOL_SPECS)
            if not result["tool_calls"]:
                break
            messages.append(
                {
                    "role": "assistant",
                    "content": result.get("content") or "",
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"], ensure_ascii=False)},
                        }
                        for tc in result["tool_calls"]
                    ],
                }
            )
            for tc in result["tool_calls"]:
                yield {"type": "tool_call", "tool": tc["name"], "args": tc["arguments"]}
                output = T.execute_tool(tc["name"], tc["arguments"], db, user)
                save_message(db, session.id, "tool", "", tool_name=tc["name"],
                             tool_args=tc["arguments"], tool_result=output)
                yield {"type": "tool_result", "tool": tc["name"], "result": output}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(output, ensure_ascii=False)[:6000],
                    }
                )

        for piece in llm.chat_stream(messages):
            reply += piece
            yield {"type": "delta", "content": piece}
    except Exception as exc:  # noqa: BLE001
        logger.exception("流式 Agent 失败，退回本地引擎")
        yield {"type": "error", "content": f"模型调用异常：{exc}，已切换本地引擎"}
        local_reply, events = local_engine.answer(db, user, message)
        for ev in events:
            yield ev
        reply = local_reply
        for piece in _chunks(reply):
            yield {"type": "delta", "content": piece}

    if not reply:
        reply = "抱歉，我暂时没有生成有效回答，请换个说法再试一次。"
        yield {"type": "delta", "content": reply}

    save_message(db, session.id, "assistant", reply)
    yield {"type": "done", "content": reply, "session_id": session.id}


def _chunks(text: str, size: int = 24) -> Iterator[str]:
    for i in range(0, len(text), size):
        yield text[i : i + size]
