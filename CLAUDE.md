# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个 Claude Code skill（`stock-analyze`），用于自动化上市公司投资分析。支持 A股/美股/港股，通过 6 阶段流水线生成 13 章节分析报告 + HTML 可视化。核心设计：结构化数据采集（Tushare/yfinance）+ PDF 年报原文解析 + 12 大师框架审计。

## 常用命令

```bash
# 环境自检
python3 -m scripts.check_env

# 安装依赖
pip3 install --user -r scripts/requirements.txt

# 在 Claude Code 中触发分析
/stock-analyze 贵州茅台 600519.SH

# 量化监控模式
/stock-analyze 实丰文化 --monitor
```

### 关键脚本单独运行

所有 Python 模块从仓库根目录以 `python3 -m scripts.<module>` 方式运行。关键模块：

- `scripts.check_env` — 环境检查
- `scripts.data_snapshot` — 生成 9 节确定性数据
- `scripts.financial_audit` — 12 框架红旗审计
- `scripts.assemble_report` — Phase 3 五 part 拼接为 13 章节主报告
- `scripts.anti_lazy_lint` — Phase 6 四项机械规则校验
- `scripts.review_loop` — Phase 6 reviewer FIX 合并 + 对抗检测
- `scripts.build_html` — MD → HTML 转换
- `scripts.monitor` — 量化监控核心

## 架构

### 调度模式：主智能体 + 9 Sub-agent

`SKILL.md` 是协调器入口。主智能体（项目经理角色）通过 `Agent` 工具调度 sub-agent，自身不执行数据采集或报告写作。

**Sub-agent 定义在 `agents/` 目录**：
- `data-collector` — Phase 1 数据采集
- `phase3-part{1-5}` — 报告 5 part 串行写作（顺序：2→3→4→5→1）
- `reviewer-{narrative,valuation,redflag}` — Phase 6 三维度并行评审

**修正循环**：不使用 Agent resume（参数不存在），而是 fresh-restart + context injection，将上轮 FIX 列表注入新 prompt。

### 6 阶段流水线

```
Phase 1 (data-collector sub-agent) → Phase 2 (主 agent 自跑 PDF 精析)
  → Phase 3 (5 sub-agent 串行写作 + assemble_report.py 拼接)
  → Phase 6 (anti_lazy_lint → 3 reviewer 并行 → 修正循环 → HTML → GitHub Pages push)
  → [可选] Phase 7 量化监控
```

Phase 4/5 已在 v5.1.4 删除。

### Python 数据层 (`scripts/`)

23 个模块，按市场分 collector：
- `tushare_collector.py` — A 股/港股 25 个 API
- `us_collector.py` — 美股 yfinance
- `hk_collector.py` — 港股混合

数据缓存：`data_cache.py` 实现 7 天 TTL Parquet 缓存，缓存目录 `~/.claude/plugins/stock-analyze/.cache`。

### 参考文档体系 (`references/`)

- `agent-protocol.md` — Agent 工具调度协议 + Fresh-Restart 规则
- `phase-orchestration.md` — 每 Phase 详细 checklist（主 agent 必读）
- `scoring-rubric.md` / `qualitative-frameworks.md` / `valuation-frameworks.md` — 评分与估值框架（sub-agent 内部读）

### 报告模板 (`assets/`)

- `templates/report-skeleton.md` — 13 章节严格骨架
- `templates/exec-summary-schema.md` — Exec Summary 7 字段
- `html/` — HTML 渲染骨架 + CSS + 组件库

## 环境要求

- **Tushare Token**：A 股/港股必需，通过 `TUSHARE_TOKEN` 环境变量设置
- **依赖**：`tushare yfinance pypdf pandas pyarrow requests`
- 输出目录：`output/{公司名}/`（含 `raw_data/`、`reviewer_responses/` 等子目录）

## 关键设计约束

- PDF 必读：关键数据必须来自年报原文，带 `[Tushare:income.revenue]` / `[PDF:q3_2025, P.4]` 来源标签
- 数学推导 > 逻辑猜测：关键推断必须包含可独立验算的数学推导
- 12 框架审计产出的 ≥2 个 🔴 致命红旗触发快筛否决
- 定性判断使用黑白三档（看多/看空/中性-分歧），禁止百分比打分
- 信息缺口闭环：§十二 强制 ≥3 条，Phase 6 Part D 五步穷举补查
