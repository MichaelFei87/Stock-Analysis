"""stock-analyze data layer — 结构化金融数据采集、计算与报告生成.

24 个模块，按职责分层:

配置与缓存:
    config              中央配置（token、缓存路径、速率限制、输出目录）
    data_cache          7 天 TTL 的 Parquet 缓存

环境检查:
    check_env           环境自检（pip 包 + TUSHARE_TOKEN + TAVILY_API_KEY）

数据采集（按市场）:
    tushare_collector   A 股 / 港股 Tushare Pro 接口封装
    us_collector        美股 yfinance 接口封装
    hk_collector        港股混合（Tushare 港股 + yfinance fallback）
    yf_adapter          yfinance → Tushare 格式 Parquet 回填适配器
    legacy_quote        免费 K 线 fallback（新浪 JSON，无需 token）

数据搜索:
    tavily_search       Tavily Search API 封装（年报 PDF 搜索）
    pdf_reader          财报 PDF 原文解析（pypdf + 正则段落提取）

数据计算:
    derived_metrics     CAGR / FCF / ROIC / WACC / Owner Earnings 等衍生指标
    data_snapshot       9 节确定性数据快照（Phase 1 产物）
    financial_audit     12 框架红旗审计（Piotroski / Beneish / Altman / Q4 洗澡等）
    capital_flow        A 股主力控盘与资金流向分析
    technical_analysis  A 股技术分析（均线 / MACD / 布林带等）
    peer_collector      A 股可比公司自动采集（申万行业分类）

报告生成与审核:
    assemble_report     Phase 3 五 part 拼接为 13 章节主报告
    anti_lazy_lint      Phase 6 四项机械规则校验
    review_loop         Phase 6 reviewer FIX 合并 + 对抗检测
    build_html          MD → HTML 报告渲染
    update_index        GitHub Pages 主页联动

监控与解析:
    monitor             Phase 7 量化监控
    report_parser       历史报告解析（提取 tagged metrics 作 baseline）
    lessons_manager     全局经验库管理（append / recent）

CLI 入口: python3 -m scripts.<module>（从仓库根目录运行）
数据输出到 output/{company}/raw_data/ 下。
"""

__version__ = "5.1.4"
