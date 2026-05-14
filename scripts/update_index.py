"""Stock-Analysis-Reports 主页联动 (v4.6).

解决 Phase 6 Part C 痛点: 每份新报告都要手工编辑 index.html 加卡片。
v4.6 改为自动:
1. 从主报告 MD 抽取卡片元数据(ticker / 评分 / 结论 / 收益 / 日期 等)
2. 写到 output/{company}/card-metadata.json
3. 若指定 --repo, 自动合并到 Stock-Analysis-Reports/data/reports.json (upsert by ticker)

Usage:
    # 只生成 card-metadata.json (不改 Stock-Analysis-Reports)
    python3 -m scripts.update_index --company 实丰文化

    # 生成并 upsert 到 Stock-Analysis-Reports
    python3 -m scripts.update_index --company 实丰文化 \\
        --repo /tmp/Stock-Analysis-Reports-v2

    # 强制覆盖现有报告 (by ticker match)
    python3 -m scripts.update_index --company 实丰文化 \\
        --repo /tmp/Stock-Analysis-Reports-v2
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


# ---------- 解析工具 ----------

def _find_latest_md(company_dir: Path) -> Path:
    """找 output/{company}/ 下最新的 {company}-analysis-{date}.md"""
    candidates = sorted(company_dir.glob(f"{company_dir.name}-analysis-*.md"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"未找到 {company_dir}/*-analysis-*.md")
    return candidates[0]


def _grep(text: str, pattern: str, group: int = 1, default: str = "") -> str:
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(group).strip() if m else default


def _grep_float(text: str, pattern: str, default: float | None = None) -> float | None:
    s = _grep(text, pattern)
    if not s:
        return default
    # 去掉 % 或其他单位
    s = re.sub(r"[^\d.\-+]", "", s)
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


# ---------- 语气推断 ----------

def _infer_tone(verdict: str, score: float | None) -> str:
    """根据 verdict 文本 + 评分推断 tone(bullish/neutral/bearish)."""
    v = (verdict or "").lower()
    if any(k in v for k in ["强烈看好", "推荐买入", "买入"]):
        return "bullish"
    if any(k in v for k in ["看空", "回避", "减仓"]):
        return "bearish"
    if "中性-分歧偏空" in verdict or "偏空" in v:
        return "bearish"
    if "有条件看好" in v or "看多" in v:
        return "bullish"
    # 退化到评分判断
    if score is not None:
        if score >= 6.0:
            return "bullish"
        if score < 4.0:
            return "bearish"
    return "neutral"


def _detect_market(ticker: str, company_name: str) -> str:
    t = (ticker or "").upper()
    # 带后缀的优先精确匹配
    if re.search(r"\.(SH|SZ|BJ)$", t):
        return "a"
    if re.search(r"\.HK$", t):
        return "hk"
    if re.search(r"\.US$", t):
        return "us"
    # 无后缀 fallback: 6位纯数字 → A股
    if re.match(r"^\d{6}$", t):
        return "a"
    # 4-5位纯数字 → 港股
    if re.match(r"^\d{4,5}$", t):
        return "hk"
    # 1-5位纯字母 → 美股 (仅在有 ticker 时)
    if t and re.match(r"^[A-Z]{1,5}$", t):
        return "us"
    return "unknown"


# ---------- 元数据提取 ----------

@dataclass
class CardMetadata:
    slug: str = ""
    ticker: str = ""
    name: str = ""
    name_cn: str = ""
    sector: str = ""
    market: str = ""
    report_date: str = ""
    version: str = "v1"
    composite_score: float | None = None
    verdict: str = ""
    verdict_tone: str = "neutral"
    valuation_tag: str = ""
    one_liner: str = ""
    metrics: list[dict] = None
    expected_return_short: str = ""
    badges: list[dict] = None

    def __post_init__(self):
        if self.metrics is None:
            self.metrics = []
        if self.badges is None:
            self.badges = []


def _slug_from_company(company_name: str, ticker: str) -> str:
    """根据 Stock-Analysis-Reports 现有命名惯例: EnglishName_中文名."""
    # 已有映射表(历史兼容)
    known = {
        "闻泰科技": "Wingtech_闻泰科技",
        "实丰文化": "ShifengCulture_实丰文化",
        "震安科技": "ZhenAn_震安科技",
        "西藏矿业": "TibetMining_西藏矿业",
        "纽瑞芯": "NewRadioTech_纽瑞芯",
        "程星通信": "Starway_程星通信",
        "同泰怡": "Tongtaiyi_同泰怡",
    }
    if company_name in known:
        return known[company_name]
    # fallback: ticker_company — ticker 必须有效(非空且非纯符号)
    clean_ticker = re.sub(r"\.(SH|SZ|BJ|HK|US)$", "", ticker or "", flags=re.I).strip()
    if not clean_ticker:
        # ticker 缺失时用公司名拼音首字母或直接用中文名,避免 X_ 前缀
        print(f"[WARN] ticker 为空,slug 使用公司名: {company_name}")
        return company_name
    return f"{clean_ticker}_{company_name}"


def _parse_structured_block(text: str, block_name: str) -> dict[str, str]:
    """解析 report-skeleton v4.6 的 HTML 注释块,如 <!-- CARD_METADATA: key: val\n ... -->"""
    m = re.search(rf"<!--\s*{block_name}:?(.*?)-->", text, re.DOTALL)
    if not m:
        return {}
    body = m.group(1)
    result = {}
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("{{"):  # 跳过未填充的 placeholder 行
            continue
        kv = re.match(r"([a-z_]+)\s*:\s*(.+?)(?:\s*\(.*\))?$", line)
        if kv:
            key, val = kv.group(1), kv.group(2).strip()
            if val and not val.startswith("{{"):
                result[key] = val
    return result


def _load_phase1_meta(company_dir: Path) -> dict:
    """Load structured meta.json written by Phase 1 data collector (if exists)."""
    for candidate in [company_dir / "raw_data" / "meta.json", company_dir / "meta.json"]:
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
    return {}


def _normalize_verdict(verdict_cn: str) -> str:
    """Normalize Chinese verdict text to English enum."""
    v = (verdict_cn or "").strip()
    if not v or v == "–":
        return v
    bullish_kw = ["强烈看好", "推荐买入", "买入", "看多", "有条件看好", "看好"]
    bearish_kw = ["看空", "回避", "减仓", "卖出", "偏空"]
    neutral_kw = ["中性", "持有", "观望"]
    for kw in bullish_kw:
        if kw in v:
            return "Bullish"
    for kw in bearish_kw:
        if kw in v:
            return "Bearish"
    for kw in neutral_kw:
        if kw in v:
            return "Neutral"
    # Already English or unrecognized — return as-is
    return v



def extract_metadata(md_path: Path, company_name: str) -> CardMetadata:
    text = md_path.read_text(encoding="utf-8")

    meta = CardMetadata()
    meta.name_cn = company_name

    # Phase 1 structured metadata — authoritative source for ticker/market/industry
    p1 = _load_phase1_meta(md_path.parent)
    meta.name = p1.get("name_en") or company_name

    # v4.6: 优先解析 HTML 注释中的结构化 metadata 块(Phase 3 写报告时填入)
    card_block = _parse_structured_block(text, "CARD_METADATA")
    rating_block = _parse_structured_block(text, "RATING_TRIO_DATA")

    # 文件名推 ticker + date
    fname = md_path.stem  # 如 "实丰文化-analysis-2026-04-24"
    date_m = re.search(r"(\d{4}-\d{2}-\d{2})", fname)
    if date_m:
        meta.report_date = date_m.group(1)

    # Ticker: Phase 1 meta.json is authoritative
    title = _grep(text, r"^#\s+(.+)$")
    if p1.get("ticker"):
        meta.ticker = p1["ticker"]
        print(f"[INFO] ticker 从 meta.json 提取: {meta.ticker}")
    else:
        # fallback: Title 抽 ticker: # xxx(002862.SZ)投资分析报告
        ticker_m = re.search(r"\(([^)]*\.(SH|SZ|BJ|HK|US)[^)]*)\)", title)
        if ticker_m:
            meta.ticker = ticker_m.group(1).strip()
        else:
            tm = re.search(r"\b(\d{6}\.(SH|SZ|BJ)|[A-Z]{1,5}\.US|\d{1,5}\.HK|\d{6})\b", title)
            if tm:
                meta.ticker = tm.group(1)

    # fallback 2: CARD_METADATA 块中的 ticker 字段
    if not meta.ticker and card_block.get("ticker"):
        meta.ticker = card_block["ticker"].strip()
        print(f"[INFO] ticker 从 CARD_METADATA 块提取: {meta.ticker}")

    # fallback 3: 全文搜索带后缀的 ticker
    if not meta.ticker:
        tm_full = re.search(r"\b(\d{6}\.(SH|SZ|BJ)|[A-Z]{1,5}\.US|\d{1,5}\.HK)\b", text)
        if tm_full:
            meta.ticker = tm_full.group(1)
            print(f"[INFO] ticker 从报告正文提取: {meta.ticker}")

    if not meta.ticker:
        print(f"[WARN] 未能从报告提取 ticker,slug/market 可能不准确")

    meta.market = p1.get("market") or _detect_market(meta.ticker, company_name)
    meta.slug = _slug_from_company(company_name, meta.ticker)

    # 版本号(从 title 后的 v4.1 等)或从正文找最末的 "v4.1 修订"
    vm = re.search(r"\bv(\d+\.\d+)\b", title) or re.search(r"附录.*v(\d+\.\d+)", text)
    if vm:
        meta.version = f"v{vm.group(1)}"

    # 综合评分
    score = _grep_float(text, r"综合评分\*?\*?:?\s*\*?\*?([\d.]+)\s*/\s*10")
    if score is None:
        score = _grep_float(text, r"综合评分\*?\*?:?\s*\*?\*?([\d.]+)")
    meta.composite_score = score

    # 投资方向(verdict)
    verdict = _grep(text, r"投资方向综合判定\*?\*?:?\s*\*?\*?([^\n*]+)")
    if not verdict:
        verdict = _grep(text, r"\*\*综合评分\*\*:\s*\*?\*?[\d.]+/10\*?\*?\s*·\s*\*?\*?([^\n*]+)")
    if not verdict:
        # 从"一句话结论"的粗体前缀找
        verdict = _grep(text, r"\*\*一句话结论\*\*:\s*\*\*([^*]+)\*\*")
    meta.verdict = _normalize_verdict(verdict) if verdict else "–"
    meta.verdict_tone = _infer_tone(verdict, score)

    # 估值锚 / 期望收益
    anchor_price = rating_block.get("anchor_price") or _grep(text, r"估值锚\*?\*?:?\s*\*?\*?[^\n元]*?([\d.]+)\s*元")
    if anchor_price:
        try:
            ap = float(re.sub(r"[^\d.]", "", anchor_price))
            meta.valuation_tag = f"估值锚 {ap} 元"
        except ValueError:
            pass

    # 期望收益: 优先从 rating block, 其次从 §十 投资回报表格
    ret_raw = rating_block.get("expected_return") or _grep(
        text, r"\*\*概率加权\s*\d*\s*年?\s*收益率\*\*\s*\|[^\|]+\|[^\|]+\|\s*\*\*([+\-−]?[\d.]+)%?\*\*"
    )
    if not ret_raw:
        # fallback: 查找 "年化 ≈ X%" 或 "期望收益 -X%" 格式
        ret_raw = _grep(text, r"2\s*年\s*期望收益率?\*?\*?\s*\|[^\n]*?([+\-−]?[\d.]+)%")
    if ret_raw:
        clean = re.sub(r"[^\d.+\-]", "", ret_raw)
        if clean:
            meta.expected_return_short = f"{clean}%"

    # 一句话结论
    one_liner = _grep(text, r"\*\*一句话结论\*\*:\s*(.+?)(?=\n\n|\n\*\*|$)", 1, "")
    # 清理 markdown 加粗
    one_liner = re.sub(r"\*\*([^*]+)\*\*", r"\1", one_liner)
    one_liner = re.sub(r"\s+", " ", one_liner).strip()
    meta.one_liner = one_liner[:300]  # 截断

    # 业务领域(sector) — 优先 Phase 1 meta.json, 其次 CARD_METADATA 块, 最后正文推断
    sector = p1.get("industry") or card_block.get("sector")
    if not sector:
        # 从 title 或 副标题括号里找业务关键词
        # 优先: 主报告 §四 业务板块表或 §一"一句话结论"开头"XX 是..." / title 注释括号
        sector_patterns = [
            # title 行: "(002862.SZ · 玩具 + 游戏 + 光伏参股)" 等
            r"[•·]\s*([^\|\n•·]{2,40}?)(?:\s*\(|$|\n)",
            # §一: "一句话结论: 看空 — 某某业务..."
            r"\*\*行业\*\*:\s*([^\n|]+)",
            r"\*\*主营业务[^\*]*\*\*:\s*([^\n|]+)",
        ]
        for pat in sector_patterns:
            s = _grep(text, pat)
            s = s.strip(" |*·—").strip()
            # 过滤掉明显不是行业的(包含 "市场共识"/"评分" 等)
            if s and len(s) > 2 and not any(kw in s for kw in ["市场共识", "评分", "元", "亿", "%", "**"]):
                sector = s
                break
    meta.sector = (sector or "–")[:80]

    # 3 个 metrics 卡片(复用 §二 评分总览或§九估值锚)
    metrics = []
    if score is not None:
        metrics.append({"label": "综合评分", "value": f"{score}/10", "tone": "neutral"})
    if meta.expected_return_short:
        try:
            val = float(meta.expected_return_short.strip("%").replace("+", ""))
            tone = "positive" if val > 0 else "negative" if val < -10 else "neutral"
        except (ValueError, TypeError):
            tone = "neutral"
        metrics.append({"label": "期望收益", "value": meta.expected_return_short, "tone": tone})
    if meta.valuation_tag:
        # 从 valuation_tag 抽纯数字
        num = re.search(r"([\d.]+)\s*元", meta.valuation_tag)
        if num:
            metrics.append({"label": "估值锚", "value": f"{num.group(1)}元", "tone": "neutral"})
    # PB 补充(如能找到) — 限定在 header 的"总市值: X 亿 · PB Y.ZZ" 行,避开 "2024 年" 这种年份
    # 用更严格正则:PB 后跟空格再数字(小数点 1-3 位),避免匹配到 "PB 2024"
    pb_m = re.search(r"\bPB\s+([0-9]{1,3}\.[0-9]{1,3})(?:\s|x|$)", text)
    if pb_m and len(metrics) < 3:
        metrics.append({"label": "PB", "value": f"{pb_m.group(1)}x", "tone": "neutral"})
    meta.metrics = metrics[:3]

    # badges
    meta.badges = [
        {"label": f"{meta.verdict} {score}/10" if score else meta.verdict, "variant": "amber"},
    ]
    if meta.valuation_tag:
        meta.badges.append({"label": meta.valuation_tag, "variant": "amber"})

    return meta


# ---------- reports.json upsert ----------

def upsert_reports_json(repo_data_json: Path, card: CardMetadata) -> bool:
    """合并 card 到 reports.json. 返回是否新增(True)或更新(False)."""
    if repo_data_json.exists():
        data = json.loads(repo_data_json.read_text(encoding="utf-8"))
    else:
        data = {"schema_version": "v1", "reports": []}

    reports = data.setdefault("reports", [])
    card_dict = asdict(card)

    existing_idx = None
    for i, r in enumerate(reports):
        if r.get("ticker") == card.ticker and r.get("slug") == card.slug:
            existing_idx = i
            break

    if existing_idx is not None:
        reports[existing_idx] = card_dict
        is_new = False
    else:
        reports.append(card_dict)
        is_new = True

    # 按 report_date 降序
    reports.sort(key=lambda r: r.get("report_date", ""), reverse=True)

    data["last_updated"] = card.report_date
    repo_data_json.parent.mkdir(parents=True, exist_ok=True)
    repo_data_json.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return is_new


# ---------- 主入口 ----------

def main():
    ap = argparse.ArgumentParser(description="Stock-Analysis-Reports 主页卡片元数据自动化 (v4.6)")
    ap.add_argument("--company", required=True, help="公司目录名, 例 实丰文化")
    ap.add_argument("--output-dir", help="output 根目录 (默认 output/)")
    ap.add_argument("--repo", help="Stock-Analysis-Reports 仓库路径 (例 /tmp/Stock-Analysis-Reports-v2). 若指定则自动 upsert reports.json")
    ap.add_argument("--html", help="HTML 报告路径 (自动复制为 reports/{slug}/分析报告_dashboard.html)")
    ap.add_argument("--force", action="store_true", help="(已废弃,无效果) 现在总是覆盖")
    args = ap.parse_args()

    output_root = Path(args.output_dir) if args.output_dir else None
    # 搜索 output 目录 — 优先选含主报告 md 的,而非仅 exists 的
    candidates = []
    if output_root:
        candidates.append(output_root / args.company)
    candidates.extend([
        Path(f"output/{args.company}"),
        Path.home() / ".claude" / "plugins" / "stock-analyze" / "output" / args.company,
        Path.home() / ".claude" / "skills" / "stock-analyze" / "output" / args.company,
    ])
    company_dir = None
    md_path = None
    for c in candidates:
        if c.exists():
            mds = sorted(c.glob(f"{c.name}-analysis-*.md"), reverse=True)
            if mds:
                company_dir = c
                md_path = mds[0]
                break
    if md_path is None:
        print(
            f"❌ 未找到主报告 {args.company}-analysis-*.md, 已尝试: "
            f"{[str(c) for c in candidates]}",
            file=sys.stderr,
        )
        return 1

    print(f"📖 解析: {md_path}")
    try:
        card = extract_metadata(md_path, args.company)
    except Exception as e:
        print(f"❌ 解析失败: {e}", file=sys.stderr)
        import traceback; traceback.print_exc()
        return 1

    # 写 card-metadata.json
    card_json = company_dir / "card-metadata.json"
    card_json.write_text(
        json.dumps(asdict(card), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✅ 写入 {card_json}")
    print(f"   ticker={card.ticker} · score={card.composite_score} · verdict={card.verdict} · tone={card.verdict_tone}")

    # 若指定 --repo,合并到 reports.json + 复制文件到 reports/{slug}/
    if args.repo:
        repo = Path(args.repo)
        if not repo.exists():
            print(f"⚠️  {repo} 不存在,跳过 upsert")
            return 0
        data_json = repo / "data" / "reports.json"
        report_dir = repo / "reports" / card.slug
        report_dir.mkdir(parents=True, exist_ok=True)

        # 复制 card-metadata.json
        target_card = report_dir / "card-metadata.json"
        target_card.write_text(card_json.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"✅ 复制到 {target_card}")

        # 复制 HTML 报告到 reports/{slug}/分析报告_dashboard.html
        # (render.js 默认用此文件名)
        html_src = args.html
        if not html_src:
            # 自动查找 output/{company}/ 下的 HTML
            html_candidates = sorted(company_dir.glob("*.html"), reverse=True)
            if html_candidates:
                html_src = str(html_candidates[0])
        if html_src:
            src = Path(html_src)
            if src.exists():
                target_html = report_dir / "分析报告_dashboard.html"
                import shutil
                shutil.copy2(src, target_html)
                print(f"✅ 复制 HTML → {target_html}")
            else:
                print(f"⚠️  HTML 源文件不存在: {src}")
        else:
            print(f"⚠️  未找到 HTML 报告,跳过 HTML 复制")

        is_new = upsert_reports_json(data_json, card)
        action = "新增" if is_new else "更新"
        print(f"✅ {action} reports.json 条目 (ticker={card.ticker})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
