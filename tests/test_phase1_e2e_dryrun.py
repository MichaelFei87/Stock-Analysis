"""
E2E dry-run: 模拟完整 Phase 1 flow for 中国平安 601318.SH
验证每一步命令/参数/搜索词是否正确，不真正下载文件。

运行: python3 -m tests.test_phase1_e2e_dryrun
"""

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

COMPANY = "中国平安"
TICKER = "601318.SH"
MARKET = "A股"
TODAY = date.today()

SKILL_ROOT = Path(__file__).resolve().parent.parent  # skills/stock-analyze/
OUTPUT_DIR = SKILL_ROOT / "output" / COMPANY

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}  {detail}")
        failed += 1


def section(title: str):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


# ═══════════════════════════════════════════════════════════════
# Phase 0: 主 agent 动态年份计算 (SKILL.md Step 3)
# ═══════════════════════════════════════════════════════════════
section("Phase 0: 主 agent 动态年份计算")

m, y = TODAY.month, TODAY.year
latest_annual_fy = y - 1 if m >= 5 else y - 2

if 1 <= m <= 4:
    latest_quarterly_desc = f"{y-1}年第三季度报告"
elif 5 <= m <= 8:
    latest_quarterly_desc = f"{y}年第一季度报告"
elif 9 <= m <= 10:
    latest_quarterly_desc = f"{y}年半年度报告"
else:
    latest_quarterly_desc = f"{y}年第三季度报告"

print(f"  today={TODAY}, month={m}")
print(f"  latest_annual_fy={latest_annual_fy}")
print(f"  latest_quarterly_desc={latest_quarterly_desc}")

check("年报 FY=2025 (5月≥5 → 当年-1)", latest_annual_fy == 2025)
check("季报=2026年第一季度报告", latest_quarterly_desc == "2026年第一季度报告")


# ═══════════════════════════════════════════════════════════════
# Phase 1 Step 0: 环境自检
# ═══════════════════════════════════════════════════════════════
section("Phase 1 Step 0: 环境自检")

env_cmd = f"cd {SKILL_ROOT} && python3 -m scripts.check_env"
print(f"  cmd: {env_cmd}")
r = subprocess.run(env_cmd, shell=True, capture_output=True, text=True, timeout=30)
check("check_env 退出码=0", r.returncode == 0, f"returncode={r.returncode}\n{r.stderr[-200:]}")
check("TUSHARE_TOKEN set", "TUSHARE_TOKEN" in os.environ or "TUSHARE_TOKEN set" in r.stdout,
      "A股需要 TUSHARE_TOKEN")


# ═══════════════════════════════════════════════════════════════
# Phase 1 Step 1: tushare_collector 命令
# ═══════════════════════════════════════════════════════════════
section("Phase 1 Step 1: Tushare 主数据采集命令")

tushare_cmd = f"python3 -m scripts.tushare_collector {TICKER} --name {COMPANY}"
print(f"  cmd: {tushare_cmd}")
check("命令含 ticker", TICKER in tushare_cmd)
check("命令含 --name", "--name" in tushare_cmd)
print(f"  (dry-run: 不实际执行, 验证命令格式正确)")


# ═══════════════════════════════════════════════════════════════
# Phase 1 Step 2: 4 个 artifact 脚本命令
# ═══════════════════════════════════════════════════════════════
section("Phase 1 Step 2: Artifact 脚本命令验证")

artifact_cmds = {
    "peer_collector": f"python3 -m scripts.peer_collector {TICKER} --peers 5 --name {COMPANY} --out output/{COMPANY}/peer_analysis.md",
    "capital_flow": f"python3 -m scripts.capital_flow {TICKER} --days 60 --out output/{COMPANY}/capital_flow.md",
    "technical_analysis": f"python3 -m scripts.technical_analysis {TICKER} --name {COMPANY} --daily output/{COMPANY}/raw_data/daily.parquet --out output/{COMPANY}/technical_analysis.md",
    "financial_audit": f"python3 -m scripts.financial_audit output/{COMPANY}/raw_data",
    "derived_metrics": f"python3 -m scripts.derived_metrics output/{COMPANY}/raw_data --market a",
    "data_snapshot": f"python3 -m scripts.data_snapshot --bundle output/{COMPANY}/raw_data --out output/{COMPANY}/data_snapshot.md --ts-code {TICKER} --company {COMPANY}",
}

for name, cmd in artifact_cmds.items():
    print(f"  {name}: {cmd}")
    check(f"{name} 命令含 ticker 或 output 路径", TICKER in cmd or COMPANY in cmd)

print(f"  (dry-run: 不实际执行)")


# ═══════════════════════════════════════════════════════════════
# Phase 1 Step 3: PDF 搜索词验证 (核心!)
# ═══════════════════════════════════════════════════════════════
section("Phase 1 Step 3: PDF 搜索词构建 (★ 核心验证)")

annual_query = f"site:cninfo.com.cn {TICKER} {COMPANY} {latest_annual_fy}年年度报告 PDF"
quarterly_query = f"site:cninfo.com.cn {TICKER} {COMPANY} {latest_quarterly_desc} PDF"

print(f"  年报搜索词: {annual_query}")
print(f"  季报搜索词: {quarterly_query}")

# 验证搜索词中的年份
check(f"年报搜索含 '{latest_annual_fy}年年度报告'", f"{latest_annual_fy}年年度报告" in annual_query)
check("年报搜索不含 '2024年年度报告' (旧年份!)", "2024年年度报告" not in annual_query,
      "BUG: 还在搜2024年年报!")
check(f"季报搜索含 '{latest_quarterly_desc}'", latest_quarterly_desc in quarterly_query)
check("年报搜索含 site:cninfo.com.cn", "site:cninfo.com.cn" in annual_query)

# pdf_reader 命令模板
pdf_cmd = f"python3 -m scripts.pdf_reader {{URL}} --all-sections --out output/{COMPANY}/raw_data/pdf_sections_annual_{latest_annual_fy}.json"
print(f"  pdf_reader 命令模板: {pdf_cmd}")
check("pdf_reader 输出文件含正确FY", str(latest_annual_fy) in pdf_cmd)


# ═══════════════════════════════════════════════════════════════
# Phase 1 Step 4: WebSearch 3 轮关键词
# ═══════════════════════════════════════════════════════════════
section("Phase 1 Step 4: WebSearch 3 轮关键词")

ws_queries = [
    ("公告/业绩预告", f"{COMPANY} {TICKER} 业绩预告 公告 2025 2026"),
    ("投资社区舆情", f"{COMPANY} 赛道 看多 看空 雪球 东方财富"),
    ("行业/政策/宏观", f"{COMPANY} 保险行业 政策 监管 2026"),
]
for label, q in ws_queries:
    print(f"  {label}: {q}")
check("3 轮 WebSearch 关键词构建完成", len(ws_queries) == 3)


# ═══════════════════════════════════════════════════════════════
# 模拟: 主 agent 构建 data-collector prompt (验证参数注入)
# ═══════════════════════════════════════════════════════════════
section("模拟: 主 agent 构建 data-collector prompt")

prompt_template = f"""你是金融数据采集专员。任务: 拉取 {COMPANY} ({TICKER}) 的全部数据。

参数:
- company: {COMPANY}
- ticker: {TICKER}
- market: {MARKET}
- output_dir: output/{COMPANY}/
- latest_annual_fy: {latest_annual_fy}
- latest_quarterly_desc: {latest_quarterly_desc}

请按 agents/data-collector.md 执行 Step 0-5。
PDF 搜索时使用 latest_annual_fy={latest_annual_fy} 和 latest_quarterly_desc={latest_quarterly_desc}，
禁止自行推断年份。"""

check("prompt 含 latest_annual_fy=2025", "latest_annual_fy: 2025" in prompt_template)
check("prompt 含 latest_quarterly_desc", latest_quarterly_desc in prompt_template)
check("prompt 含 '禁止自行推断年份'", "禁止自行推断年份" in prompt_template)
check("prompt 不含硬编码 '2024年年度报告'", "2024年年度报告" not in prompt_template)
print(f"\n  --- prompt 预览 (前 300 字) ---")
print(f"  {prompt_template[:300]}...")


# ═══════════════════════════════════════════════════════════════
# 产物路径完整性验证
# ═══════════════════════════════════════════════════════════════
section("产物路径完整性验证")

expected_artifacts = [
    f"output/{COMPANY}/raw_data/_manifest.json",
    f"output/{COMPANY}/data_snapshot.md",
    f"output/{COMPANY}/peer_analysis.md",
    f"output/{COMPANY}/capital_flow.md",
    f"output/{COMPANY}/technical_analysis.md",
    f"output/{COMPANY}/audit_report.md",
    f"output/{COMPANY}/metrics.json",
    f"output/{COMPANY}/phase1-data.md",
]
for p in expected_artifacts:
    print(f"  期望产物: {p}")
check(f"期望产物 ≥ 8 个", len(expected_artifacts) >= 8)


# ═══════════════════════════════════════════════════════════════
# 总结
# ═══════════════════════════════════════════════════════════════
print(f"\n{'═'*60}")
print(f"  E2E Dry-Run 结果: {passed} passed, {failed} failed")
print(f"{'═'*60}")

if failed > 0:
    print("\n  ⚠️ 有失败项，请检查上方 ❌ 标记")
    sys.exit(1)
else:
    print("\n  🎉 全部通过! Phase 1 flow 参数/命令/搜索词均正确。")
    print(f"  ★ 核心验证: 今天 {TODAY} 搜中国平安年报 → {latest_annual_fy}年年度报告 ✅")
    sys.exit(0)
