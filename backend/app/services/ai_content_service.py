"""对接 AI 接口：按客户姓名、模版内容生成邮件文案。支持 OpenAI 兼容 API（如 ChatAnywhere）。"""
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# 请求超时（秒），522/连接超时多为网络或源站慢，适当加大
AI_REQUEST_TIMEOUT = 90.0
# 失败后重试次数（仅对超时、5xx 重试）
AI_MAX_RETRIES = 3


def get_content_for_preview(
    customer_name: str | None = None,
    region: str | None = None,
    company_traits: str | None = None,
    template: str | None = None
) -> str:
    """
    从 AI API 获取邮件文案。
    传入参数：客户姓名、区域、公司特点（表格前三列）、模版内容。
    """
    surname = (customer_name or "").strip()
    customer = f"{surname[0]}总" if surname else "（未指定）"
    prompt = (
        "角色：湃乐多航运科技资深营销总监，擅长极简高阶B2B邮件\n"
        "风格：克制、专业、轻价值驱动、语气专业但不生硬，带温度和价值感\n"
        "输出格式：只输出完整邮件，不要加任何说明、不要加```、不要解释\n"
        "字数硬性要求：整封邮件（不含称呼+落款）在70字~100字之间\n"
        "禁止：感叹号、emoji、过度恭维词、促销味重的形容词\n"
        "必须包含：收件人称呼 + 价值点 + 轻推动\n"
        "无需落款。\n"
        "以下是本次邮件的上下文：\n"
    )
    if template or customer or region or company_traits:
        prompt += "\n"
        if template:
            prompt += f"模版内容：{template}。围绕这次的模版内容，进行主要邮件营销内容的创作。\n"
        if customer:
            prompt += f"客户姓名：{customer}\n"
        if region:
            prompt += f"客户所在区域：{region}\n"
        # if company_traits:
        #     prompt += f"公司特点：{company_traits}"
    prompt += "最后可以加一句，我司专业为货代公司提供换单系统等自动化解决方案，我们的产品能有效提升客户的工作效率，降低运营成本。请根据以上要求，创作一封邮件。"

    if not settings.ai_api_base_url or not settings.ai_api_key:
        logger.info("AI: 未配置 base_url 或 key，返回占位")
        return _placeholder_content(customer_name, region, company_traits, template)

    url = settings.ai_api_base_url.rstrip("/")
    # OpenAI 兼容：发到 /chat/completions
    if url.endswith("/v1"):
        url = f"{url}/chat/completions"
    elif not url.endswith("/chat/completions"):
        url = f"{url.rstrip('/')}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.ai_api_key}",
    }
    body = {
        "model": settings.ai_api_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
    }
    logger.info("AI: 请求 url=%s model=%s prompt_len=%s", url, settings.ai_api_model, len(prompt))
    try:
        with httpx.Client(timeout=AI_REQUEST_TIMEOUT) as client:
            for attempt in range(AI_MAX_RETRIES + 4):
                try:
                    r = client.post(url, json=body, headers=headers)
                    logger.info("AI: 响应 status=%s (attempt %s)", r.status_code, attempt + 1)
                    r.raise_for_status()
                    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                    choices = data.get("choices") or []
                    if choices and isinstance(choices[0], dict):
                        msg = choices[0].get("message") or {}
                        content = msg.get("content") or ""
                        if isinstance(content, str) and content.strip():
                            logger.info("AI: 成功 content_len=%s", len(content))
                            return content.strip()
                    out = data.get("content", data.get("text", str(data)) if isinstance(data, dict) else str(data))
                    logger.info("AI: 使用兼容字段 content_len=%s", len(str(out)))
                    return out
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    if attempt < AI_MAX_RETRIES:
                        time.sleep(1.0 * (attempt + 1))
                        logger.warning("AI: 超时/连接错误，第 %s 次重试: %s", attempt + 1, e)
                    else:
                        raise
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < 3:
                        time.sleep(5.0)
                        logger.warning("AI: 429 限流，等待 5s 后第 %s 次重试", attempt + 1)
                    elif e.response.status_code >= 500 and attempt < AI_MAX_RETRIES:
                        time.sleep(1.0 * (attempt + 1))
                        logger.warning("AI: 服务端错误 %s，第 %s 次重试", e.response.status_code, attempt + 1)
                    else:
                        raise
    except Exception as e:
        logger.exception("AI API 调用失败，已回退为占位文案")
        placeholder = _placeholder_content(customer_name, region, company_traits, template)
        hint = _error_hint(e)
        return f"{placeholder}\n\n[调试] API 报错: {type(e).__name__}: {e}{hint}"


def _error_hint(exc: Exception) -> str:
    """根据异常类型返回简短处理建议（如 522/超时）。"""
    msg = str(exc).lower()
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 522:
        return "\n\n处理建议：522 表示连接源站超时。可尝试：1) 检查本机网络/代理；2) 更换为国内可访问的 OpenAI 兼容 API；3) 稍后重试。"
    if "522" in msg or "origin timed out" in msg or ("connect" in msg and "timeout" in msg):
        return "\n\n处理建议：522 多为连接源站超时。可尝试：1) 检查本机网络/代理；2) 更换为国内可访问的 OpenAI 兼容 API（如国内中转）；3) 稍后重试。"
    if "timeout" in msg or "timeout" in type(exc).__name__.lower():
        return "\n\n处理建议：请求超时。可适当增加超时时间或更换更稳定的 API 地址。"
    return ""


def _placeholder_content(
    customer_name: str | None,
    region: str | None,
    company_traits: str | None,
    template: str | None
) -> str:
    """占位预览：用表格前三列（客户姓名、区域、公司特点）生成一封示例文案。"""
    parts = ["【占位预览】此为邮件预览文案，对接 AI 接口后将按表格前三列生成真实内容。"]
    parts.append(f"客户姓名：{customer_name or '—'}")
    parts.append(f"区域：{region or '—'}")
    parts.append(f"公司特点：{company_traits or '—'}")
    if template:
        parts.append(f"模版：{template}")
    parts.append("请配置 ai_api_base_url 与 ai_api_key 对接实际 AI 接口。")
    return "\n".join(parts)
