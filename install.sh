#!/bin/bash
#
# Claude Code 投资分析 Skill — 一键安装
#
# 使用方法：
#   curl -fsSL https://raw.githubusercontent.com/MichaelFei87/Stock-Analysis/main/install.sh | bash
#
# 幂等：重复运行可查漏补缺，已有文件会被覆盖为最新版本。
# 自动发现：通过 GitHub API 获取文件树，无需手动维护文件列表。
#

set -e

SKILL_DIR="$HOME/.claude/skills/stock-analyze"
REPO_OWNER="MichaelFei87"
REPO_NAME="Stock-Analysis"
REPO_URL="https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/main"
API_URL="https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/git/trees/main?recursive=1"

echo "================================================"
echo "  Claude Code — 投资分析 Skill 安装程序"
echo "  sub-agent 架构 + 结构化数据 + PDF 精析"
echo "  支持 A 股 / 美股 / 港股"
echo "================================================"
echo ""

# ------------------------------------------------
# [1/4] 获取仓库文件树
# ------------------------------------------------
echo "[1/4] 从 GitHub API 获取文件树..."
TREE_JSON=$(curl -fsSL "$API_URL")

if [ -z "$TREE_JSON" ] || echo "$TREE_JSON" | grep -q '"message"'; then
    echo "❌ 无法获取仓库文件树，请检查网络或 GitHub API 限流"
    echo "   提示: 可加 GITHUB_TOKEN 提高限额"
    exit 1
fi

# 提取所有 blob 路径（排除不需安装的文件）
FILES=$(echo "$TREE_JSON" | python3 -c "
import json, sys
tree = json.load(sys.stdin)['tree']
skip = {'install.sh', 'CLAUDE.md', 'README.md', 'CHANGELOG.md', 'LICENSE', '.gitignore', '.github'}
for item in tree:
    if item['type'] != 'blob':
        continue
    path = item['path']
    top = path.split('/')[0]
    if path in skip or top.startswith('.'):
        continue
    # 跳过测试文件
    if '/tests/' in path or top == 'tests':
        continue
    print(path)
")

if [ -z "$FILES" ]; then
    echo "❌ 文件树解析失败"
    exit 1
fi

# ------------------------------------------------
# [2/4] 创建目录结构
# ------------------------------------------------
echo "[2/4] 创建目录结构..."
echo "$FILES" | while IFS= read -r f; do
    dir=$(dirname "$f")
    if [ "$dir" != "." ]; then
        mkdir -p "$SKILL_DIR/$dir"
    fi
done
mkdir -p "$HOME/投资报告"

# ------------------------------------------------
# [3/4] 下载所有文件
# ------------------------------------------------
TOTAL=$(echo "$FILES" | wc -l | tr -d ' ')
echo "[3/4] 下载 $TOTAL 个文件..."

COUNT=0
FAIL=0
echo "$FILES" | while IFS= read -r f; do
    COUNT=$((COUNT + 1))
    if curl -fsSL "$REPO_URL/$f" -o "$SKILL_DIR/$f" 2>/dev/null; then
        printf "  [%d/%d] ✓ %s\n" "$COUNT" "$TOTAL" "$f"
    else
        printf "  [%d/%d] ✗ %s\n" "$COUNT" "$TOTAL" "$f"
        FAIL=$((FAIL + 1))
    fi
done

# ------------------------------------------------
# [4/4] 验证
# ------------------------------------------------
echo ""
echo "[4/4] 验证安装..."

PHASE_COUNT=$(find "$SKILL_DIR/phases" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
REF_COUNT=$(find "$SKILL_DIR/references" -name "*.md" 2>/dev/null ! -name "*.LEGACY.md" | wc -l | tr -d ' ')
SCRIPT_COUNT=$(find "$SKILL_DIR/scripts" -maxdepth 1 -name "*.py" 2>/dev/null | wc -l | tr -d ' ')
ASSETS_COUNT=$(find "$SKILL_DIR/assets" -type f 2>/dev/null | wc -l | tr -d ' ')
AGENT_COUNT=$(find "$SKILL_DIR/agents" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')

echo ""
echo "============================================"
echo "  ✅ 安装完成！"
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
echo "  3. 配置 Tavily Search（强烈推荐，注册 https://tavily.com）:"
echo "     echo 'export TAVILY_API_KEY=\"tvly-your_key_here\"' >> ~/.zshrc"
echo "     source ~/.zshrc"
echo ""
echo "  4. 环境自检:"
echo "     cd $SKILL_DIR && python3 -m scripts.check_env"
echo ""
echo "  5. 重启 Claude Code，然后使用："
echo ""
echo "     /stock-analyze <公司名称>"
echo "     /stock-analyze <公司名称> --monitor   # 量化监控"
echo ""
