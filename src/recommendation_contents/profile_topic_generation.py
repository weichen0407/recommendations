"""Generate many stage-one questions from fixed role, industry and JTBD triples."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from .brief_generation import response_text
from .brief_schema import (
    LANGUAGES,
    MAX_BRIEFS,
    SCHEMA_VERSION,
    build_brief_schema,
    load_brief_catalog,
    parse_brief_response,
    validate_briefs,
)

PROFILE_TOPIC_RULES = """你是推荐内容运营选题编辑。输入是固定的目标受众三元组，而不是某位用户的个人资料。
为该 role、industry、jtbd 组合生成指定数量的不同研究问题。

要求：
1. 每条 title 必须是一句自然、明确、以问号结尾的问题，可直接展示给用户。
2. description 用一个完整句子说明工作视角、对象或范围、具体任务和预期产出；不提前写答案。
3. audience 必须逐字复制输入的 role、industry、jtbd，不得重新分类或改成 other。
4. tags 必须来自所给的精简目录，并满足 industry→segment→object、JTBD→task→perspective/output 关系。
5. 同一三元组内尽量覆盖不同的细分行业、技术对象、任务、视角、决策场景和产出；不能只替换标题措辞。
6. role 的首选视角优先。没有可兼容首选视角时，可以采用任务允许的其他视角，并在 rationale 解释原因。
7. 不编造公司事实、市场数据、专利结论或个人项目材料。补充的应用场景、地区、时间窗口和工况写入 assumptions。
8. 输出只是节点 1 的问题和结构化标签，不包含 summary、最终执行 prompt、curl、HTML 或工具调用要求。
9. title、description、rationale、assumptions 使用请求语言；枚举 key 保持英文原值。
10. 仅返回符合 schema 的 JSON，不加 Markdown 或说明。
"""


def validate_profile_request(request: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    catalog = load_brief_catalog()
    audience = request.get("audience")
    language, count = request.get("language", "zh-CN"), request.get("count", 10)
    errors = []
    if not isinstance(audience, dict) or set(audience) != {"role", "industry", "jtbd"}:
        errors.append("audience must contain exactly role, industry and jtbd")
        audience = {}
    for key in ("role", "industry", "jtbd"):
        allowed = {row["value"] for row in catalog["audience"][key]}
        if audience.get(key) not in allowed:
            errors.append(f"audience.{key} must be an allowed enum")
    role, jtbd = audience.get("role"), audience.get("jtbd")
    if role in catalog["role_allowed_jtbd"] and jtbd not in catalog["role_allowed_jtbd"][role]:
        errors.append("audience.jtbd is not enabled for audience.role")
    if language not in LANGUAGES:
        errors.append("language must be zh-CN or en")
    if type(count) is not int or not 1 <= count <= MAX_BRIEFS:
        errors.append(f"count must be an integer between 1 and {MAX_BRIEFS}")
    return {key: audience.get(key, "") for key in ("role", "industry", "jtbd")}, errors


def generate_profile_topics(
    request: dict[str, Any], get_model: Callable[[], Any]
) -> dict[str, Any]:
    audience, errors = validate_profile_request(request)
    language, count = request.get("language", "zh-CN"), request.get("count", 10)
    catalog = load_brief_catalog()
    focused = _focused_catalog(catalog, audience) if not errors else catalog
    normalized = {"audience": audience, "language": language, "count": count}
    raw, attempts, briefs = "", 0, []
    if not errors:
        for attempt in range(2):
            attempts += 1
            try:
                raw = response_text(
                    get_model().invoke(
                        _profile_messages(
                            normalized,
                            focused,
                            previous_response=raw if attempt else None,
                            errors=errors,
                        )
                    )
                )
            except Exception as exc:  # noqa: BLE001 - model-provider boundary
                errors = [f"LLM request failed ({type(exc).__name__}); check model configuration."]
                break
            try:
                candidate = parse_brief_response(raw)
                errors = validate_briefs(candidate, focused, count)
                errors.extend(_profile_semantic_errors(candidate, audience))
            except (ValueError, RecursionError):
                errors = ["Response must be a JSON object with unique keys."]
            if not errors:
                briefs = [{"brief_id": str(uuid4()), **brief} for brief in candidate["briefs"]]
                break
    return {
        "status": "failed" if errors else "succeeded",
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": catalog["taxonomy_version"],
        "generation_id": str(uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": normalized,
        "attempts": attempts,
        "briefs": briefs,
        "errors": errors,
    }


def all_profile_triples(catalog: dict[str, Any] | None = None) -> list[dict[str, str]]:
    catalog = catalog or load_brief_catalog()
    industries = [row["value"] for row in catalog["audience"]["industry"]]
    return [
        {"role": role, "industry": industry, "jtbd": jtbd}
        for role, jtbd_values in catalog["role_allowed_jtbd"].items()
        for jtbd in jtbd_values
        for industry in industries
    ]


def triple_id(audience: dict[str, str]) -> str:
    return "__".join(audience[key] for key in ("role", "industry", "jtbd"))


def _focused_catalog(catalog: dict[str, Any], audience: dict[str, str]) -> dict[str, Any]:
    tasks = [
        row
        for row in catalog["jtbd_tasks"]
        if row["value"] in catalog["jtbd_allowed_tasks"][audience["jtbd"]]
    ]
    task_perspectives = {p for row in tasks for p in row["allowed_perspectives"]}
    preferred = set(catalog["role_preferred_perspectives"][audience["role"]])
    perspectives = task_perspectives & preferred or task_perspectives
    outputs = {value for row in tasks for value in row["allowed_outputs"]}
    segments = [
        row for row in catalog["industry_segments"] if row["entry_industry"] == audience["industry"]
    ]
    segment_values = {row["value"] for row in segments}
    objects = [
        row
        for row in catalog["technology_objects"]
        if segment_values.intersection(row["allowed_segments"])
    ]
    focused = dict(catalog)
    focused["audience"] = {
        key: [row for row in catalog["audience"][key] if row["value"] == audience[key]]
        for key in ("role", "industry", "jtbd")
    }
    focused["role_perspectives"] = [
        row for row in catalog["role_perspectives"] if row["value"] in perspectives
    ]
    focused["industry_segments"] = segments
    focused["technology_objects"] = objects
    focused["jtbd_tasks"] = tasks
    focused["desired_outputs"] = [
        row for row in catalog["desired_outputs"] if row["value"] in outputs
    ]
    focused["role_preferred_perspectives"] = {
        audience["role"]: catalog["role_preferred_perspectives"][audience["role"]]
    }
    focused["role_allowed_jtbd"] = {audience["role"]: [audience["jtbd"]]}
    focused["jtbd_allowed_tasks"] = {
        audience["jtbd"]: catalog["jtbd_allowed_tasks"][audience["jtbd"]]
    }
    return focused


def _profile_messages(
    request: dict[str, Any],
    catalog: dict[str, Any],
    previous_response: str | None,
    errors: list[str],
) -> list[dict[str, str]]:
    compact_keys = {
        "value",
        "label_zh",
        "label_en",
        "definition",
        "boundary",
        "entry_industry",
        "allowed_segments",
        "allowed_perspectives",
        "allowed_outputs",
    }
    compact = {
        "role_preferred_perspectives": catalog["role_preferred_perspectives"],
        "jtbd_allowed_tasks": catalog["jtbd_allowed_tasks"],
    }
    for key in (
        "role_perspectives",
        "industry_segments",
        "technology_objects",
        "jtbd_tasks",
        "desired_outputs",
    ):
        compact[key] = [{k: v for k, v in row.items() if k in compact_keys} for row in catalog[key]]
    schema = build_brief_schema(catalog, request["count"])
    schema["description"] = (
        "Stage 1 for a fixed target-audience triple. Every brief must preserve the supplied "
        "role, industry and JTBD, and its title must be a displayable question."
    )
    system = (
        PROFILE_TOPIC_RULES
        + "\n本三元组可用的精简目录：\n"
        + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
        + "\n响应 schema：\n"
        + json.dumps(schema, ensure_ascii=False)
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
    ]
    if previous_response is not None:
        messages.extend(
            [
                {"role": "assistant", "content": previous_response[:40000]},
                {
                    "role": "user",
                    "content": "修复以下错误并重新返回全部问题："
                    + json.dumps(errors, ensure_ascii=False),
                },
            ]
        )
    return messages


def _profile_semantic_errors(payload: Any, audience: dict[str, str]) -> list[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("briefs"), list):
        return []
    errors, titles = [], set()
    for index, brief in enumerate(payload["briefs"]):
        if not isinstance(brief, dict):
            continue
        if brief.get("audience") != audience:
            errors.append(f"$.briefs[{index}].audience must exactly match the input triple")
        title = brief.get("title")
        normalized = " ".join(title.split()).casefold() if isinstance(title, str) else ""
        if not normalized.endswith(("?", "？")):
            errors.append(f"$.briefs[{index}].title must be a question ending in ? or ？")
        if normalized in titles:
            errors.append(f"$.briefs[{index}].title duplicates another question")
        titles.add(normalized)
    return errors
