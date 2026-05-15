"""
E2E test: 验证主 agent 动态年份计算 → data-collector prompt 注入 → PDF 搜索关键词正确。
用中国平安 601318.SH 作为例子，不真正下载文件。

运行: python3 -m tests.test_dynamic_year
"""

from datetime import date


# ── Step 1: 复现 SKILL.md 主 agent 的年份计算逻辑 ──────────────────────

def calc_latest_annual_fy(today: date) -> int:
    """SKILL.md Step 3 关键规则: 月份≥5 → 当年-1, 否则 当年-2"""
    if today.month >= 5:
        return today.year - 1
    else:
        return today.year - 2


def calc_latest_quarterly_desc(today: date) -> str:
    """SKILL.md Step 3 关键规则: 基于月份推断最新已披露季报"""
    m = today.month
    y = today.year
    if 1 <= m <= 4:
        return f"{y-1}年第三季度报告"
    elif 5 <= m <= 8:
        return f"{y}年第一季度报告"
    elif 9 <= m <= 10:
        return f"{y}年半年度报告"
    else:  # 11-12
        return f"{y}年第三季度报告"


# ── Step 2: 模拟 data-collector 收到参数后构建的搜索关键词 ──────────────

def build_search_queries(company: str, ticker: str,
                         latest_annual_fy: int, latest_quarterly_desc: str) -> dict:
    """复现 agents/data-collector.md Step 3A 定位 PDF URL"""
    return {
        "annual": f"site:cninfo.com.cn {ticker} {company} {latest_annual_fy}年年度报告 PDF",
        "quarterly": f"site:cninfo.com.cn {ticker} {company} {latest_quarterly_desc} PDF",
    }


# ── Step 3: 测试用例 ─────────────────────────────────────────────────

def run_tests():
    company = "中国平安"
    ticker = "601318.SH"

    test_cases = [
        # (today, expected_fy, expected_quarterly_desc, 说明)
        (date(2026, 5, 14), 2025, "2026年第一季度报告",   "★ 当前实际日期: 5月≥5 → FY2025 + Q1"),
        (date(2026, 3, 10), 2024, "2025年第三季度报告",   "3月<5 → FY2024 + 上年Q3"),
        (date(2026, 1, 15), 2024, "2025年第三季度报告",   "1月<5 → FY2024 + 上年Q3"),
        (date(2026, 4, 30), 2024, "2025年第三季度报告",   "4月<5 → FY2024 (年报还没出齐)"),
        (date(2026, 5, 1),  2025, "2026年第一季度报告",   "5月≥5 → FY2025 (年报已出)"),
        (date(2026, 8, 20), 2025, "2026年第一季度报告",   "8月 → FY2025 + Q1"),
        (date(2026, 9, 5),  2025, "2026年半年度报告",     "9月 → FY2025 + 半年报"),
        (date(2026, 10, 31),2025, "2026年半年度报告",     "10月 → FY2025 + 半年报"),
        (date(2026, 11, 1), 2025, "2026年第三季度报告",   "11月 → FY2025 + Q3"),
        (date(2026, 12, 25),2025, "2026年第三季度报告",   "12月 → FY2025 + Q3"),
        (date(2027, 4, 15), 2025, "2026年第三季度报告",   "2027年4月 → FY2025 (2026年报还没出齐)"),
        (date(2027, 5, 1),  2026, "2027年第一季度报告",   "2027年5月 → FY2026 (年报已出)"),
    ]

    passed = 0
    failed = 0

    print(f"{'='*70}")
    print(f"动态年份 E2E 测试 — {company} ({ticker})")
    print(f"{'='*70}\n")

    for today, exp_fy, exp_q_desc, desc in test_cases:
        fy = calc_latest_annual_fy(today)
        q_desc = calc_latest_quarterly_desc(today)
        queries = build_search_queries(company, ticker, fy, q_desc)

        fy_ok = (fy == exp_fy)
        q_ok = (q_desc == exp_q_desc)
        all_ok = fy_ok and q_ok

        status = "✅ PASS" if all_ok else "❌ FAIL"
        print(f"{status}  {today}  {desc}")
        print(f"       FY: {fy} {'✅' if fy_ok else f'❌ expected {exp_fy}'}")
        print(f"       季报: {q_desc} {'✅' if q_ok else f'❌ expected {exp_q_desc}'}")
        print(f"       → 年报搜索: {queries['annual']}")
        print(f"       → 季报搜索: {queries['quarterly']}")
        print()

        if all_ok:
            passed += 1
        else:
            failed += 1

    # ── 重点验证: 今天 (2026-05-14) 的实际搜索词 ──
    print(f"{'='*70}")
    print(f"★ 关键验证: 今天 {date.today()} 搜中国平安年报，年份是多少？")
    print(f"{'='*70}")
    real_fy = calc_latest_annual_fy(date.today())
    real_q = calc_latest_quarterly_desc(date.today())
    real_queries = build_search_queries(company, ticker, real_fy, real_q)
    print(f"  latest_annual_fy    = {real_fy}")
    print(f"  latest_quarterly    = {real_q}")
    print(f"  年报搜索词: {real_queries['annual']}")
    print(f"  季报搜索词: {real_queries['quarterly']}")

    if real_fy == 2024:
        print(f"\n  ❌❌❌ 搜2024年年报?! 现在都2026年5月了，2025年报早就出了！BUG!")
        failed += 1
    elif real_fy == 2025:
        print(f"\n  ✅ 正确! 2026年5月应该搜2025年年报。")
        passed += 1
    else:
        print(f"\n  ⚠️ 意外值: {real_fy}")
        failed += 1

    print(f"\n{'='*70}")
    print(f"结果: {passed} passed, {failed} failed, {passed+failed} total")
    print(f"{'='*70}")
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
