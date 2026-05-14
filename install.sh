#!/bin/bash
#
# Claude Code 投资分析 Skill — 一键安装 (v5.1.4)
#
# 使用方法：
#   curl -fsSL https://raw.githubusercontent.com/MichaelFei87/Stock-Analysis/main/install.sh | bash
#
# 幂等：重复运行可查漏补缺，已有文件会被覆盖为最新版本。
#

set -e

SKILL_DIR="$HOME/.claude/skills/stock-analyze"
REPO_URL="https://raw.githubusercontent.com/MichaelFei87/Stock-Analysis/main"
VERSION="5.1.4"

echo "================================================"
echo "  Claude Code — 投资分析 Skill 安装程序 v${VERSION}"
echo "  sub-agent 架构 + 结构化数据 + PDF 精析"
echo "  支持 A 股 / 美股 / 港股"
echo "================================================"
echo ""

# ------------------------------------------------
# [1/6] 创建目录结构
# ------------------------------------------------
echo "[1/6] 创建目录结构..."
mkdir -p "$SKILL_DIR/phases"
mkdir -p "$SKILL_DIR/references"
mkdir -p "$SKILL_DIR/scripts"
mkdir -p "$SKILL_DIR/agents"
mkdir -p "$SKILL_DIR/assets/templates"
mkdir -p "$SKILL_DIR/assets/html"
mkdir -p "$SKILL_DIR/assets/validation"
mkdir -p "$HOME/投资报告"

# ------------------------------------------------
# [2/6] 下载协调器 + 附加文件
# ------------------------------------------------
echo "[2/6] 下载协调器..."
curl -fsSL "$REPO_URL/SKILL.md" -o "$SKILL_DIR/SKILL.md"
curl -fsSL "$REPO_URL/.env.sample" -o "$SKILL_DIR/.env.sample"

# ------------------------------------------------
# [3/6] 下载 5 个阶段文件
# ------------------------------------------------
echo "[3/6] 下载 5 个阶段文件..."
for phase in \
    phase1-data-collection \
    phase2-document-analysis \
    phase3-analysis-report \
    phase6-review-publish \
    phase7-quantitative-monitor; do
  curl -fsSL "$REPO_URL/phases/${phase}.md" -o "$SKILL_DIR/phases/${phase}.md"
done

# ------------------------------------------------
# [4/6] 下载参考文档 (7 个)
# ------------------------------------------------
echo "[4/6] 下载 7 个参考文档..."
for ref in \
    scoring-rubric \
    qualitative-frameworks \
    valuation-frameworks \
    search-strategy \
    html-template-guide \
    agent-protocol \
    phase-orchestration; do
  curl -fsSL "$REPO_URL/references/${ref}.md" -o "$SKILL_DIR/references/${ref}.md"
done

# ------------------------------------------------
# [5/6] 下载 assets/
# ------------------------------------------------
echo "[5/6] 下载 assets/..."
# 2 个模板
curl -fsSL "$REPO_URL/assets/templates/report-skeleton.md"     -o "$SKILL_DIR/assets/templates/report-skeleton.md"
curl -fsSL "$REPO_URL/assets/templates/exec-summary-schema.md" -o "$SKILL_DIR/assets/templates/exec-summary-schema.md"
# 3 个 HTML
curl -fsSL "$REPO_URL/assets/html/base.html"       -o "$SKILL_DIR/assets/html/base.html"
curl -fsSL "$REPO_URL/assets/html/styles.css"      -o "$SKILL_DIR/assets/html/styles.css"
curl -fsSL "$REPO_URL/assets/html/components.html" -o "$SKILL_DIR/assets/html/components.html"
# 2 个 validation
curl -fsSL "$REPO_URL/assets/validation/report-checklist.json"     -o "$SKILL_DIR/assets/validation/report-checklist.json"
curl -fsSL "$REPO_URL/assets/validation/insight-card-schema.json"  -o "$SKILL_DIR/assets/validation/insight-card-schema.json"

# ------------------------------------------------
# [6/6] 下载 Python 数据层
# ------------------------------------------------
echo "[6/6] 下载 Python 数据层（scripts/）+ Agent 定义..."
for py in \
    __init__ \
    config \
    check_env \
    data_cache \
    tushare_collector \
    us_collector \
    hk_collector \
    pdf_reader \
    derived_metrics \
    financial_audit \
    report_parser \
    monitor \
    peer_collector \
    capital_flow \
    technical_analysis \
    update_index \
    build_html \
    data_snapshot \
    anti_lazy_lint \
    assemble_report \
    legacy_quote \
    lessons_manager \
    review_loop; do
  curl -fsSL "$REPO_URL/scripts/${py}.py" -o "$SKILL_DIR/scripts/${py}.py"
done
curl -fsSL "$REPO_URL/scripts/requirements.txt" -o "$SKILL_DIR/scripts/requirements.txt"

# Agent 定义 (v5.0+)
echo "  下载 Agent 定义..."
for agent in \
    data-collector \
    phase3-part1 \
    phase3-part2 \
    phase3-part3 \
    phase3-part4 \
    phase3-part5 \
    reviewer-narrative \
    reviewer-redflag \
    reviewer-valuation; do
  curl -fsSL "$REPO_URL/agents/${agent}.md" -o "$SKILL_DIR/agents/${agent}.md"
done

# ------------------------------------------------
# 验证
# ------------------------------------------------
PHASE_COUNT=$(find "$SKILL_DIR/phases" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
REF_COUNT=$(find "$SKILL_DIR/references" -name "*.md" 2>/dev/null ! -name "*.LEGACY.md" | wc -l | tr -d ' ')
SCRIPT_COUNT=$(find "$SKILL_DIR/scripts" -maxdepth 1 -name "*.py" 2>/dev/null | wc -l | tr -d ' ')
ASSETS_COUNT=$(find "$SKILL_DIR/assets" -type f 2>/dev/null | wc -l | tr -d ' ')
AGENT_COUNT=$(find "$SKILL_DIR/agents" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')

# v5.1.4 期望: 5 phases + 7 refs + 23 scripts + 7 assets + 9 agents
EXPECT_PHASES=5
EXPECT_REFS=7
EXPECT_SCRIPTS=23
EXPECT_ASSETS=7
EXPECT_AGENTS=9

ERRORS=""
[ "$PHASE_COUNT"  -ne "$EXPECT_PHASES"  ] && ERRORS="${ERRORS}  phases:  期望=${EXPECT_PHASES} 实际=${PHASE_COUNT}\n"
[ "$REF_COUNT"    -ne "$EXPECT_REFS"    ] && ERRORS="${ERRORS}  refs:    期望=${EXPECT_REFS} 实际=${REF_COUNT}\n"
[ "$SCRIPT_COUNT" -ne "$EXPECT_SCRIPTS" ] && ERRORS="${ERRORS}  scripts: 期望=${EXPECT_SCRIPTS} 实际=${SCRIPT_COUNT}\n"
[ "$ASSETS_COUNT" -ne "$EXPECT_ASSETS"  ] && ERRORS="${ERRORS}  assets:  期望=${EXPECT_ASSETS} 实际=${ASSETS_COUNT}\n"
[ "$AGENT_COUNT"  -ne "$EXPECT_AGENTS"  ] && ERRORS="${ERRORS}  agents:  期望=${EXPECT_AGENTS} 实际=${AGENT_COUNT}\n"

if [ -z "$ERRORS" ]; then
    echo ""
    echo "============================================"
    echo "  ✅ 安装成功！(v${VERSION})"
    echo "============================================"
    echo ""
    echo "  协调器:  SKILL.md"
    echo "  阶段:    $PHASE_COUNT 个 (phases/)"
    echo "  框架:    $REF_COUNT 个 (references/)"
    echo "  脚本:    $SCRIPT_COUNT 个 Python 模块 (scripts/)"
    echo "  资产:    $ASSETS_COUNT 个 (assets/)"
    echo "  Agent:   $AGENT_COUNT 个 (agents/)"
    echo "  输出目录: ~/投资报告/"
    echo ""
    echo "============================================"
    echo "  下一步（必做，否则 A 股/港股分析无法工作）"
    echo "============================================"
    echo ""
    echo "  1. 安装 Python 依赖:"
    echo "     cd $SKILL_DIR/scripts && pip3 install --user -r requirements.txt"
    echo ""
    echo "  2. 配置 Tushare Token（注册 https://tushare.pro/register）:"
    echo "     echo 'export TUSHARE_TOKEN=\"your_token_here\"' >> ~/.zshrc"
    echo "     source ~/.zshrc"
    echo ""
    echo "  3. 环境自检:"
    echo "     cd $SKILL_DIR && python3 -m scripts.check_env"
    echo ""
    echo "  4. 重启 Claude Code，然后使用："
    echo ""
    echo "     /stock-analyze <公司名称>"
    echo "     /stock-analyze <公司名称> --monitor   # 量化监控"
    echo ""
else
    echo ""
    echo "⚠️  安装完成但计数不匹配（可重复运行以修复）："
    echo -e "$ERRORS"
    echo "  提示: 重新运行此脚本可自动补全缺失文件"
    exit 1
fi
