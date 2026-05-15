# Claude Code 投资分析 Skill

> **结构化数据 + PDF 原文 + 11 大师框架自动审计** 的专业投资分析技能
>
> 支持 A 股 / 美股 / 港股 · 6 阶段流水线 + 量化监控 · 适用于 Anthropic Claude Code

<p align="center">
  <img src="https://img.shields.io/badge/markets-A%E8%82%A1%20%7C%20%E7%BE%8E%E8%82%A1%20%7C%20%E6%B8%AF%E8%82%A1-green" alt="markets">
  <img src="https://img.shields.io/badge/audit-11%20frameworks-orange" alt="frameworks">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="license">
</p>

**在线报告示例**: [MichaelFei87.github.io/Stock-Analysis-Reports](https://MichaelFei87.github.io/Stock-Analysis-Reports)

---

## 核心能力

| 能力 | 说明 |
|------|------|
| **结构化金融数据** | Tushare Pro（A/港股） + yfinance（美股），25+ 个 bundle 自动采集到本地 Parquet |
| **PDF 原文解析** | `pypdf` 自动抓取年报/季报，提取 9 类关键段落（利润表变动原因 / 子公司业绩 / MD&A / 风险因素 / 非经常性损益 / 前十大股东 / 资产负债变动 / 现金流变动 / 主要会计数据）|
| **11 大师框架审计** | Piotroski F-Score · Beneish M-Score · Altman Z-Score · DuPont · Buffett Quality · Sloan Accrual · Governance · Shareholder Flow · Forward Guidance · **Valuation (PB-ROE Gordon 错配 + 历史分位)** · Related-Party Exposure — 一条命令扫出 15-20 个红旗 |
| **差异化洞察** | 主报告 §十二 信息缺口闭环 + §十三 数据可审计性，Phase 6 Part D 5 步穷举补查 |
| **量化监控 (`--monitor`)** | 手动触发，对比基线指标 × 最新数据，输出"维持 / 建议复评 / 重大修订" |
| **缺口闭环补查** | §十二 信息缺口强制 ≥ 3 条，Phase 6 Part D 5 步穷举（巨潮 → 官网 → PDF → Google → Tushare API）|

---

## 🧭 4+1 阶段流水线

```
Step 0-2：环境自检 + 输入确认 + 建目录
   ↓
Phase 1 数据采集       （Tushare + yfinance + PDF 下载解析）
   ↓
Phase 2 文档精析       （精读 PDF 9 段落，提取原文引用）
   ↓
Phase 3 综合分析与报告 （13 章节主报告 + Step 1.5 自动跑 11 框架 audit）
   ↓
Phase 6 审核发布       （18 项审核 + Part D 补查闭环 + HTML + GitHub Pages）

    [可选，手动触发] ↓
Phase 7 量化监控       （/stock-analyze <公司> --monitor）
```

完整流程 / 质量门控 / 异常处理见 [SKILL.md](./SKILL.md)。

---

## 快速开始

### 1. 安装 skill

```bash
curl -fsSL https://raw.githubusercontent.com/MichaelFei87/Stock-Analysis/main/install.sh | bash
```

这会克隆到 `~/.claude/skills/stock-analyze/` 并创建 `~/投资报告/` 输出目录。

### 2. 安装 Python 依赖

```bash
cd ~/.claude/skills/stock-analyze/scripts
pip3 install --user -r requirements.txt
```

依赖：`tushare yfinance pypdf pandas pyarrow requests`

### 3. 配置 Tushare Token（A 股 / 港股必需）

注册 [tushare.pro](https://tushare.pro/register)，获取 token（建议申请学生权限获 5000+ 免费积分；或购买 2000 积分约 ¥200 解锁所有核心财报接口）。

```bash
echo 'export TUSHARE_TOKEN="your_token_here"' >> ~/.zshrc
source ~/.zshrc
```

> ⚠️ **千万别把 token 提交到 git**。[`.env.sample`](./.env.sample) 是模板；实际 token 写到 `~/.zshrc`（不在仓库内）。
>
> 💡 **友情提醒**：如果需要付费 token 并且认识作者，可以 offline 找我要 token。

### 4. 环境自检

```bash
cd ~/.claude/skills/stock-analyze
python3 -m scripts.check_env
```

全部 `[OK]` + `TUSHARE_TOKEN set` → 可用。

### 5. 启动分析

在 Claude Code 对话里：

```
/stock-analyze 实丰文化
```

或提供股票代码（加速）：

```
/stock-analyze 贵州茅台 600519.SH
```

量化监控（基于历史基线报告）：

```
/stock-analyze 实丰文化 --monitor
```

---

## 📂 仓库结构

```
Stock-Analysis/
├── README.md                   # 本文件
├── CHANGELOG.md                # v1 → v5.1.4 演进
├── LICENSE                     # MIT
├── .env.sample                 # 环境变量模板
├── SKILL.md                    # ⭐ 协调器（6+1 阶段定义）
├── install.sh / uninstall.sh   # 一键安装 / 卸载
│
├── phases/                     # 5 个阶段执行指令
│   ├── phase1-data-collection.md
│   ├── phase2-document-analysis.md
│   ├── phase3-analysis-report.md
│   ├── phase6-review-publish.md
│   └── phase7-quantitative-monitor.md
│
├── references/                 # 7 个参考文档
│   ├── scoring-rubric.md           # 10 维度事实评分
│   ├── qualitative-frameworks.md   # 3 定性框架（v4.1）
│   ├── valuation-frameworks.md     # Damodaran 估值
│   ├── search-strategy.md          # WebSearch 辅助规范
│   ├── html-template-guide.md      # HTML 可视化规范
│   ├── agent-protocol.md           # Agent 工具调度协议
│   └── phase-orchestration.md      # 每 Phase 详细 checklist
│
├── agents/                     # 9 个 sub-agent 定义
│   ├── data-collector.md
│   ├── phase3-part{1-5}.md     # 报告 5 part 写作
│   ├── reviewer-narrative.md
│   ├── reviewer-valuation.md
│   └── reviewer-redflag.md
│
├── assets/                     # 模板 + HTML + 校验 schema
│   ├── templates/
│   │   ├── report-skeleton.md      # 13 章节严格骨架
│   │   └── exec-summary-schema.md  # Exec Summary 7 字段
│   ├── html/
│   │   ├── base.html               # HTML 骨架
│   │   ├── styles.css              # CSS
│   │   └── components.html         # 组件片段库
│   └── validation/
│       ├── report-checklist.json   # 审核清单
│       └── insight-card-schema.json
│
└── scripts/                    # ⭐ Python 数据层（23 模块 + 5 测试）
    ├── config.py               # Token / 缓存 / 速率
    ├── check_env.py            # 环境自检
    ├── data_cache.py           # 7 天 TTL Parquet 缓存
    ├── tushare_collector.py    # A 股 25 个 API
    ├── us_collector.py         # 美股 yfinance
    ├── hk_collector.py         # 港股混合
    ├── pdf_reader.py           # 财报 PDF 9 段落精析
    ├── derived_metrics.py      # CAGR / FCF / ROIC / Owner Earnings
    ├── financial_audit.py      # ⭐ 11 大师框架异常审计
    ├── peer_collector.py       # 同行业可比公司
    ├── capital_flow.py         # 主力控盘与资金流
    ├── technical_analysis.py   # MA/MACD/RSI/布林带
    ├── data_snapshot.py        # 9 节确定性数据
    ├── assemble_report.py      # Phase 3 5 part 拼接
    ├── anti_lazy_lint.py       # Phase 6 4 项机械规则
    ├── review_loop.py          # Phase 6 reviewer FIX 合并
    ├── lessons_manager.py      # 经验库管理
    ├── build_html.py           # MD → HTML 转换
    ├── update_index.py         # 主页联动 reports.json
    ├── report_parser.py        # 解析历史报告（monitor 用）
    ├── monitor.py              # ⭐ 量化监控核心
    ├── legacy_quote.py         # 旧版行情 fallback
    ├── requirements.txt
    └── README.md
```

---

## 📊 单次分析产出

```
~/投资报告/{公司名}/
├── raw_data/
│   ├── *.parquet               # Tushare/yfinance 结构化
│   ├── pdfs/*.pdf              # 下载的财报 PDF
│   ├── pdf_sections_*.json     # PDF 9 段落
│   ├── metrics.json            # 30+ 衍生指标
│   └── _manifest.json
├── phase1-data.md              # 数据采集总结
├── phase2-documents.md         # 文档精析
├── data_snapshot.md            # 9 节确定性数据
├── audit_report.md             # ⭐ 11 框架 15-20 条红旗
├── peer_analysis.md            # 同行业对标
├── capital_flow.md             # 主力控盘与资金流
├── technical_analysis.md       # 技术面分析
├── phase3-part{1-5}.md         # 5 part 分段写作
├── {公司}-analysis-{date}.md   # ⭐ 主报告（13 章节）
├── {公司}-analysis-{date}.html # ⭐ HTML 可视化
├── reviewer_responses/         # reviewer 修正档案
├── phase6-review-log.md        # 审核日志
├── main-log.md                 # 调度日志
└── monitor_{公司}_{date}.md    # 监控简报（--monitor 触发时）
```

---

## 🧠 核心设计原则

### 1. PDF 必读 + 来源可审计
**v1 踩过坑**：依赖第三方摘要（如证券之星），错误把实丰文化 Q3 亏损归因为"费用上升"；**真相**是参股公司超隆光电爆雷 88%（年报 Page 4 明确写着）。v4 起强制下载解析 PDF，关键数据带 `[Tushare:income.revenue]` / `[PDF:q3_2025, P.4]` 标签。

### 2. 数学推导 > 逻辑猜测
主报告每条关键推断必须包含可独立验算的数学推导，每步含运算符+数值+单位。

### 3. 11 大师框架防盲点
Phase 3 Step 1.5 自动跑 11 框架审计 → 红旗进入主报告 Exec Summary 风险 Top。≥ 2 个 🔴 致命红旗 → 触发快筛否决。

### 4. 定性判断禁止打分换壳
v1/v2 的 7 框架 `-2~+2` 打分制是伪定量化。v4.1 改为 **3 框架**（护城河 / 管理层 / 催化剂）逻辑三段式，**黑白三档**（看多 / 看空 / 中性-分歧），禁止百分比修正。

### 5. 缺口闭环补查
§十二 信息缺口强制 ≥3 条，每条记录"已尝试的查询路径"。Phase 6 Part D 5 步穷举（巨潮 → 官网 → PDF → Google → Tushare API），补查成功必须反写到所有相关章节。

### 6. 可监控可跟踪
Phase 7 以历史报告的带标签指标为基线，重跑数据层对比变化 ≥10% 的指标，给出"维持 / 复评 / 重大修订"。

---

## 🗂️ 与 Stock-Analysis-Reports 仓库的关系

本仓库（`Stock-Analysis`）是 **skill 代码**。

生成的 **分析报告 HTML** 发布在姊妹仓库 [MichaelFei87/Stock-Analysis-Reports](https://github.com/MichaelFei87/Stock-Analysis-Reports)，通过 GitHub Pages 在线浏览：

👉 **在线报告**: [MichaelFei87.github.io/Stock-Analysis-Reports](https://MichaelFei87.github.io/Stock-Analysis-Reports)

Phase 6 的 Part C 自动把 HTML 推到 Stock-Analysis-Reports 仓库。

---

## 📜 版本演进（详见 [CHANGELOG.md](./CHANGELOG.md)）

| 版本 | 发布 | 关键变化 |
|------|------|---------|
| **v5.1.4** | 2026-05-13 | 删 Phase 4/5（多角色+洞察），15→13 章节 |
| **v5.1.3** | 2026-05-04 | 删除不存在的 Agent.resume API + Fresh-Restart 协议 |
| **v5.1** | 2026-04-29 | 主智能体调度协议 + 9 个 sub-agent 架构 |
| **v5.0** | 2026-04-28 | sub-agent 大架构改造 |
| **v4.1** | 2026-04-24 | 激进精简 + 关键信息保护：13→9 字段 / 4→3 框架 / 独立文件职责分离 |
| **v4.0** | 2026-04-23 | Python 数据层 + 11 框架审计 + 量化监控 (Phase 7) |
| **v3.0** | 2026-04-16 | 5 阶段流水线 + 上市公司支持 + 多角色 |

---

## 🤝 贡献

欢迎 issue / PR。重点方向：
- 更多大师框架（Graham Net-Net / Lynch PEG / Piotroski G-Score）
- 更多市场（新三板 / 日股 / 欧股）
- 分析师 / 机构持仓数据源
- Notebook 示例 + 测试套件

---

## 📝 License

[MIT](./LICENSE)

---

**作者**: [@MichaelFei87](https://github.com/MichaelFei87)
