"""本地智能助手引擎（无大模型时的兜底）。

它复用与 Tool Calling 完全相同的工具层：先做意图识别，再调用真实业务工具查询
数据库，最后用自然语言组织答案。因此即使没有配置 API Key，AI 助手依然能：
查实验室、查设备、查空闲时段、查知识库、查我的预约，甚至代提交预约。
"""
from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterator

from sqlalchemy.orm import Session

from app import services
from app.ai import rag
from app.ai import tools as T
from app.models import Lab, User

# --------------------------------------------------------------------- 意图
# 顺序即优先级：创建预约必须排在查询预约之前，否则「帮我预约…」会被误判为查询。
INTENTS: list[tuple[str, str]] = [
    ("create_reservation", r"帮我(预约|预订|订)|我要预约|我想预约|预约一下|帮我订|预定|提交预约|帮我约|我要订"),
    ("my_reservations", r"我的预约|我的申请|预约记录|查询预约|查预约|预约情况|我订过|我约过|预约历史"),
    ("availability", r"有空|空闲|空档|可用时段|什么时候可以|还有位置|能不能约|可否预约|档期"),
    ("equipment", r"设备|仪器|器材|机器|装置|显微镜|服务器|工作站|示波器"),
    ("rules", r"规定|制度|规章|安全|注意|须知|流程|怎么借|如何借|违约|处罚|规范|操作要求|开放时间|申请条件"),
    ("lab_list", r"有哪些实验室|实验室列表|所有实验室|实验室有|哪些实验室|介绍一下实验室|实验室情况|实验室在哪|场地"),
]


def detect_intent(text: str) -> str:
    for name, pattern in INTENTS:
        if re.search(pattern, text):
            return name
    return "general"


# --------------------------------------------------------------------- 抽取
LAB_STOPWORDS = [
    "实验室", "我想", "我要", "帮我", "预约", "预订", "一下", "请问", "查一下", "查询",
    "看看", "有没有", "有空", "空闲", "时段", "明天", "后天", "今天", "上午", "下午",
    "晚上", "点", "到什么", "设备", "仪器", "情况", "的", "吗", "呢", "在", "哪个",
]


def extract_lab_name(db: Session, text: str, allow_fallback: bool = True) -> str | None:
    """从文本中识别实验室名称。

    先按数据库中的真实实验室名做最长匹配；匹配不到时，若 allow_fallback 为真，
    才退化为「去掉停用词后的最长片段」。注意：调用方如果不希望得到噪音结果
    （例如查设备时），应传 allow_fallback=False，只在明确提到实验室时才返回。
    """
    labs = db.query(Lab).all()

    # 1) 名称 / 编号 / 楼栋房间 直接命中
    best: tuple[int, str] | None = None
    for lab in labs:
        for cand in {lab.name, lab.code or "", (lab.building or "") + (lab.room or "")}:
            cand = (cand or "").strip()
            if len(cand) < 2:
                continue
            if cand in text:
                if best is None or len(cand) > best[0]:
                    best = (len(cand), lab.name)
            else:
                # 名称核心部分（去掉「实验室」后缀）也能匹配，如「电子电工」
                core = cand.replace("实验室", "")
                if len(core) >= 2 and core in text:
                    if best is None or len(core) > best[0]:
                        best = (len(core), lab.name)
    if best:
        return best[1]

    if not allow_fallback:
        return None

    # 2) 退化策略：去掉停用词后取最长片段（仅用于「请告诉我实验室名」这类提示）
    cleaned = text
    for word in LAB_STOPWORDS:
        cleaned = cleaned.replace(word, " ")
    tokens = [t for t in re.split(r"[\s,，。？?！!、]+", cleaned) if len(t) >= 2]
    if tokens:
        return max(tokens, key=len)
    return None


def extract_equipment_keyword(text: str) -> str:
    """从问句里抽出设备关键词。

    先剥掉疑问句式（「在哪里」「有几台」「分布在」等），再按标点切词取最长片段。
    """
    cleaned = re.sub(
        r"在哪里|在哪个实验室|在哪个|在哪儿|在哪里有|有多少台|有几台|有多少|有多少个"
        r"|分布在|有哪些|都是|请问|帮我|查询|查一下|查查|有没有|哪个实验室有|哪里能|哪儿有",
        " ",
        text,
    )
    for word in ["实验室", "设备", "仪器", "的", "吗", "呢", "？", "?", "，", "。"]:
        cleaned = cleaned.replace(word, " ")
    tokens = [t for t in re.split(r"[\s,，。？?！!、；;：:]+", cleaned) if len(t) >= 2]
    if not tokens:
        return text.strip()
    # 取最长片段；同长度时优先含字母的（如 GPU、VR）
    return max(tokens, key=lambda t: (len(t), any(c.isalpha() and c.isascii() for c in t)))


def extract_date(text: str) -> dt.date | None:
    if "大后天" in text:
        return dt.date.today() + dt.timedelta(days=3)
    if "后天" in text:
        return dt.date.today() + dt.timedelta(days=2)
    if "明天" in text or "明日" in text:
        return dt.date.today() + dt.timedelta(days=1)
    if "今天" in text or "今日" in text:
        return dt.date.today()
    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", text)
    if m:
        try:
            return dt.date(dt.date.today().year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})(?!\d)", text)
    if m:
        try:
            return dt.date(dt.date.today().year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    week = re.search(r"周([一二三四五六日天])", text)
    if week:
        target = "一二三四五六日".index(week.group(1).replace("天", "日"))
        today = dt.date.today()
        delta = (target - today.weekday()) % 7
        return today + dt.timedelta(days=delta or 7)
    return None


def _period(hour: int, text: str, idx: int) -> int:
    """根据"下午/晚上"等修饰词修正 12 小时制。"""
    window = text[max(0, idx - 6): idx]
    if any(w in window for w in ("下午", "晚上", "傍晚")) and hour < 12:
        return hour + 12
    if "中午" in window and hour < 11:
        return hour + 12
    if any(w in window for w in ("上午", "早上", "早晨")) and hour == 12:
        return 0
    return hour


def extract_time_range(text: str) -> tuple[str, str] | None:
    # 14:00-16:00 / 14:00到16:00
    m = re.search(
        r"(\d{1,2}):(\d{2})\s*(?:-|~|—|到|至|--)\s*(\d{1,2}):(\d{2})", text
    )
    if m:
        return (f"{int(m.group(1)):02d}:{m.group(2)}", f"{int(m.group(3)):02d}:{m.group(4)}")
    # 14点到16点 / 下午2点到4点
    m = re.search(
        r"(上午|下午|晚上|中午|早上)?\s*(\d{1,2})\s*[点:时]\s*(?:半|30)?\s*"
        r"(?:-|~|—|到|至)\s*(上午|下午|晚上|中午|早上)?\s*(\d{1,2})\s*[点:时]?\s*(半|30)?",
        text,
    )
    if m:
        pre1, h1, pre2, h2, half = m.groups()
        start_h = int(h1)
        end_h = int(h2)
        if pre1:
            start_h = _period(start_h, pre1 + text, 0) if pre1 in ("下午", "晚上") and start_h < 12 else start_h
        else:
            start_h = _period(start_h, text, m.start(2))
        if pre2:
            end_h = _period(end_h, pre2 + text, 0) if pre2 in ("下午", "晚上") and end_h < 12 else end_h
        else:
            end_h = _period(end_h, text, m.start(4))
        if end_h <= start_h and end_h + 12 <= 23 and start_h >= 8:
            end_h += 12
        start_m = "30" if "半" in text[m.start():m.end()] and "30" not in text[m.start():m.end()] else "00"
        end_m = "30" if half == "30" else "00"
        return (f"{start_h:02d}:{start_m}", f"{end_h:02d}:{end_m}")
    # 下午3点（单点，默认 2 小时）
    m = re.search(r"(上午|下午|晚上|中午|早上)?\s*(\d{1,2})\s*[点:时]", text)
    if m:
        pre, h = m.groups()
        hour = int(h)
        if pre in ("下午", "晚上") and hour < 12:
            hour += 12
        elif not pre:
            hour = _period(hour, text, m.start(2))
        minute = "30" if "半" in text else "00"
        end = hour + 2
        return (f"{hour:02d}:{minute}", f"{min(end, 23):02d}:{minute}")
    return None


def extract_people(text: str) -> int:
    m = re.search(r"(\d{1,3})\s*(?:个)?人", text)
    return int(m.group(1)) if m else 0


def extract_purpose(text: str) -> str:
    m = re.search(r"(?:用于|做|进行|参加|用途是|目的是)\s*([^，。；,;]{2,30})", text)
    if m:
        return m.group(1).strip()
    return ""


# --------------------------------------------------------------------- 回答生成
def _fmt_labs(data: dict) -> str:
    labs = data.get("labs") or []
    if not labs:
        return "暂时没有找到符合条件的实验室。你可以换个关键词，或者告诉我人数和用途，我帮你推荐。"
    lines = [f"共找到 {len(labs)} 间实验室："]
    for i, lab in enumerate(labs, 1):
        lines.append(
            f"{i}. **{lab['name']}**（{lab['location'] or '位置待补充'}）\n"
            f"   - 容量 {lab['capacity']} 人 · 开放 {lab['open_time']}-{lab['close_time']} · "
            f"状态 {lab['status']} · 设备 {lab['equipment_count']} 类"
        )
        if lab.get("description"):
            lines.append(f"   - {lab['description']}")
    lines.append("\n需要我帮你查某间实验室的**空闲时段**或直接**提交预约**吗？")
    return "\n".join(lines)


def _fmt_detail(data: dict) -> str:
    if not data.get("found"):
        return data.get("message", "没有找到该实验室。")
    lab = data["lab"]
    lines = [
        f"**{lab['name']}**",
        f"- 位置：{lab['location'] or '待补充'}",
        f"- 容量：{lab['capacity']} 人",
        f"- 开放时间：{lab['open_time']}-{lab['close_time']}",
        f"- 当前状态：{lab['status']}",
    ]
    if lab.get("description"):
        lines.append(f"- 简介：{lab['description']}")
    eqs = data.get("equipments") or []
    if eqs:
        lines.append("- 主要设备：" + "、".join(
            f"{e['name']}({e['quantity']}台/{e['status']})" for e in eqs[:8]
        ))
    notices = data.get("notices") or []
    if notices:
        lines.append("\n**使用须知**")
        for n in notices:
            lines.append(f"- {n['title']}：{n['content']}")
    lines.append("\n需要我查它今天的空闲时段吗？")
    return "\n".join(lines)


def _fmt_equipment(data: dict) -> str:
    items = data.get("items") or []
    if not items:
        return (
            "没有查到相关设备。"
            + (data.get("hint") or "可以换个名称试试，例如「显微镜」「服务器」「示波器」。")
        )
    lines = [f"找到 {len(items)} 条设备记录："]
    for it in items[:12]:
        lines.append(
            f"- **{it['equipment']}**（{it['model'] or '型号未登记'}）× {it['quantity']}，"
            f"状态 {it['status']}，位于 {it['lab']}（{it['lab_location'] or '位置待补充'}）"
        )
    if len(items) > 12:
        lines.append(f"…… 其余 {len(items) - 12} 条可在设备管理中查看。")
    return "\n".join(lines)


def _fmt_availability(data: dict) -> str:
    if not data.get("found"):
        return data.get("message", "没有找到该实验室。")
    ranges = data.get("free_ranges") or []
    head = f"**{data['lab']}** {data['date']}（{data['weekday']}）开放时间 {data['open_time']}-{data['close_time']}。"
    if not ranges:
        return head + "\n当天已约满，建议换个日期，我可以帮你看看明天。"
    lines = [head, "空闲时段如下："]
    for r in ranges:
        lines.append(f"- {r['start']} - {r['end']}")
    lines.append("\n需要我直接帮你预约其中某个时段吗？告诉我「帮我预约 <时间>」即可。")
    return "\n".join(lines)


def _fmt_my_reservations(data: dict) -> str:
    items = data.get("items") or []
    if not items:
        return "你目前还没有预约记录。要不要看看有哪些实验室可以约？"
    lines = [f"你共有 {data['total']} 条预约记录（最近 {len(items)} 条）："]
    for it in items:
        remark = f"，审核意见：{it['review_remark']}" if it.get("review_remark") else ""
        lines.append(
            f"- {it['booking_date']} {it['time_range']} · {it['lab_name']} · "
            f"**{it['status_text']}**{remark}"
        )
    return "\n".join(lines)


def _fmt_create(data: dict) -> str:
    if not data.get("success"):
        return f"预约没有提交成功：{data.get('message', '未知原因')}"
    r = data["reservation"]
    return (
        f"预约申请已提交 ✅\n"
        f"- 实验室：{r['lab_name']}\n"
        f"- 时间：{r['booking_date']} {r['time_range']}\n"
        f"- 人数：{r['people_count']} 人\n"
        f"- 用途：{r['purpose']}\n"
        f"- 状态：{r['status_text']}（管理员审核后生效）\n\n"
        f"你可以在「我的预约」中查看进度。"
    )


def _fmt_knowledge(db: Session, query: str) -> tuple[str, list[dict]]:
    hits = rag.search(db, query, top_k=3)
    if not hits:
        return ("知识库里暂时没有相关内容。你可以问我实验室位置、开放时间、设备情况或预约流程。", [])
    lines = ["根据实验室知识库，为你找到以下内容："]
    for i, h in enumerate(hits, 1):
        lines.append(f"\n**{i}. {h['title']}**（{h['category']}）\n{h['content']}")
    return ("\n".join(lines), hits)


# --------------------------------------------------------------------- 主入口
def answer(db: Session, user: User, text: str) -> tuple[str, list[dict]]:
    """返回 (回答文本, 过程事件列表)。事件用于前端"过程可见"。"""
    events: list[dict] = []
    intent = detect_intent(text)
    events.append({"type": "thought", "content": f"识别意图：{intent}"})

    def run(name: str, args: dict) -> dict:
        result = T.execute_tool(name, args, db, user)
        events.append({"type": "tool_call", "tool": name, "args": args})
        events.append({"type": "tool_result", "tool": name, "result": result})
        return result

    if intent == "create_reservation":
        lab_name = extract_lab_name(db, text)
        rng = extract_time_range(text)
        day = extract_date(text) or dt.date.today()
        if not lab_name:
            return ("请告诉我你想预约哪间实验室，例如「帮我预约人工智能实验室 明天 14:00-16:00」。", events)
        if not rng:
            data = run("check_availability", {"lab_name": lab_name, "date": day.isoformat()})
            return (
                f"我可以帮你预约 **{lab_name}**。请补充具体时间，例如「14:00-16:00」。\n\n"
                + _fmt_availability(data),
                events,
            )
        data = run(
            "create_reservation",
            {
                "lab_name": lab_name,
                "date": day.isoformat(),
                "start_time": rng[0],
                "end_time": rng[1],
                "purpose": extract_purpose(text) or "AI 助手代提交",
                "people_count": extract_people(text) or 1,
            },
        )
        return (_fmt_create(data), events)

    if intent == "my_reservations":
        status = ""
        for key, code in (("待审核", "pending"), ("已通过", "approved"), ("已驳回", "rejected"),
                          ("已取消", "cancelled"), ("已完成", "finished")):
            if key in text:
                status = code
                break
        return (_fmt_my_reservations(run("my_reservations", {"status": status})), events)

    if intent == "availability":
        lab_name = extract_lab_name(db, text)
        day = extract_date(text) or dt.date.today()
        if not lab_name:
            return ("请告诉我是哪间实验室，例如「人工智能实验室明天有空吗」。", events)
        return (_fmt_availability(run("check_availability", {"lab_name": lab_name, "date": day.isoformat()})), events)

    if intent == "equipment":
        # 只有在用户明确提到某间实验室时才按实验室过滤，避免把问句误当实验室名
        lab_name = extract_lab_name(db, text, allow_fallback=False) or ""
        keyword = extract_equipment_keyword(text)
        if lab_name:
            # 「XX实验室有哪些设备 / 设备清单」→ 直接列该实验室的设备
            if re.search(r"设备|仪器|器材|配置|清单", text) and (
                not keyword or keyword in lab_name or len(keyword) < 3
            ):
                data = run("get_lab_detail", {"lab_name": lab_name})
                return (_fmt_detail(data), events)
            data = run("find_equipment", {"keyword": keyword, "lab_name": lab_name})
            if not data.get("items"):
                # 该实验室没有匹配设备时，退回展示完整设备清单
                data = run("get_lab_detail", {"lab_name": lab_name})
                return (_fmt_detail(data), events)
            return (_fmt_equipment(data), events)
        data = run("find_equipment", {"keyword": keyword, "lab_name": ""})
        return (_fmt_equipment(data), events)

    if intent == "rules":
        text_ans, hits = _fmt_knowledge(db, text)
        if hits:
            events.append({"type": "tool_call", "tool": "search_knowledge", "args": {"query": text}})
            events.append({"type": "tool_result", "tool": "search_knowledge", "result": {"total": len(hits)}})
        return (text_ans, events)

    if intent == "lab_list":
        data = run("list_labs", {"keyword": "", "status": "", "min_capacity": extract_people(text) or 0})
        return (_fmt_labs(data), events)

    # 兜底：先看知识库，再看实验室概览
    hits = rag.search(db, text, top_k=2)
    if hits:
        lines = ["我从实验室知识库中找到了这些信息："]
        for h in hits:
            lines.append(f"\n**{h['title']}**（{h['category']}）\n{h['content']}")
        events.append({"type": "tool_call", "tool": "search_knowledge", "args": {"query": text}})
        events.append({"type": "tool_result", "tool": "search_knowledge", "result": {"total": len(hits)}})
        return ("\n".join(lines), events)

    data = run("list_labs", {"keyword": "", "status": "", "min_capacity": 0})
    prefix = (
        "我是实验室智能助手，可以帮你：\n"
        "1. 查询实验室位置、容量与开放时间\n"
        "2. 查询设备分布与状态\n"
        "3. 查询某天空闲时段\n"
        "4. 直接提交预约申请\n"
        "5. 检索实验室规章制度与安全须知\n\n"
        "当前实验室概览：\n"
    )
    return (prefix + _fmt_labs(data), events)


def answer_stream(db: Session, user: User, text: str) -> Iterator[dict]:
    """流式产出事件（本地引擎按句切分模拟打字机效果）。"""
    reply, events = answer(db, user, text)
    yield {"type": "start"}
    for ev in events:
        yield ev
    for piece in re.findall(r"[^\n]{1,40}\n?", reply):
        yield {"type": "delta", "content": piece}
    yield {"type": "done", "content": reply}
