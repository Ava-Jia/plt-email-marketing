"""客户表上传：解析 Excel/CSV，校验，返回行数据或错误。"""
import csv
import io
import re
from typing import Any

import openpyxl

# 表头映射：中文或英文 -> 统一 key
HEADER_MAP = {
    "客户姓名": "customer_name",
    "customer_name": "customer_name",
    "区域": "region",
    "region": "region",
    "公司特点": "company_traits",
    "company_traits": "company_traits",
    "客户邮箱": "email",
    "email": "email",
}

REQUIRED_KEYS = ["customer_name", "email"]
REQUIRED_LABELS = {
    "customer_name": "客户姓名",
    "email": "客户邮箱",
}
EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")


def _normalize_header(name: str) -> str | None:
    s = (name or "").strip()
    return HEADER_MAP.get(s) or (HEADER_MAP.get(s) if s in HEADER_MAP else None)


def _validate_email(email: str) -> bool:
    return bool(email and EMAIL_RE.match(email.strip()))


def _row_to_record(headers: list[str], row: list[Any]) -> dict[str, str] | None:
    record = {}
    for i, h in enumerate(headers):
        key = _normalize_header(h)
        if key:
            val = row[i] if i < len(row) else ""
            record[key] = str(val).strip() if val is not None else ""
    if not record:
        return None
    return record


def _validate_records(records: list[dict]) -> list[str]:
    errors = []
    for i, r in enumerate(records):
        row_num = i + 2  # 1-based + header
        for k in REQUIRED_KEYS:
            if not (r.get(k) or "").strip():
                label = REQUIRED_LABELS.get(k, k)
                errors.append(f"第 {row_num} 行：缺少必填项「{label}」")
        email = (r.get("email") or "").strip()
        if email and not _validate_email(email):
            errors.append(f"第 {row_num} 行：邮箱格式无效「{email}」")
    return errors


def parse_csv(content: bytes) -> tuple[list[dict[str, str]], list[str]]:
    """解析 UTF-8 CSV，返回 (records, errors)。"""
    try:
        text = content.decode("utf-8").strip()
    except UnicodeDecodeError:
        try:
            text = content.decode("gbk").strip()
        except Exception:
            return [], ["文件编码不支持，请使用 UTF-8 或 GBK 保存"]
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return [], ["文件为空或没有表头"]
    raw_headers = [str(h).strip() for h in rows[0]]
    headers = [_normalize_header(h) for h in raw_headers]
    if "customer_name" not in headers or "email" not in headers:
        return [], ["表头需包含「客户姓名」和「客户邮箱」列（或英文 customer_name, email）"]
    records = []
    for row in rows[1:]:
        rec = _row_to_record(raw_headers, row)
        if rec and (rec.get("customer_name") or rec.get("email")):
            records.append(rec)
    errs = _validate_records(records)
    return records, errs


def parse_xlsx(content: bytes) -> tuple[list[dict[str, str]], list[str]]:
    """解析 xlsx 第一 sheet，返回 (records, errors)。"""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as e:
        return [], [f"无法解析 Excel：{e!s}"]
    ws = wb.active
    if not ws:
        return [], ["工作簿为空"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return [], ["表格为空或没有表头"]
    raw_headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    if not raw_headers:
        return [], ["表头为空"]
    if _normalize_header(raw_headers[0]) is None and _normalize_header(raw_headers[-1]) is None:
        return [], ["表头需包含「客户姓名」和「客户邮箱」列（或英文 customer_name, email）"]
    records = []
    for row in rows[1:]:
        row_list = [str(c).strip() if c is not None else "" for c in (row or [])]
        rec = _row_to_record(raw_headers, row_list)
        if rec and (rec.get("customer_name") or rec.get("email")):
            records.append(rec)
    errs = _validate_records(records)
    return records, errs


def parse_upload(filename: str, content: bytes) -> tuple[list[dict[str, str]], list[str]]:
    """根据文件名选择解析方式，返回 (records, errors)。"""
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return parse_csv(content)
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return parse_xlsx(content)
    return [], ["仅支持 .csv 或 .xlsx 文件"]
