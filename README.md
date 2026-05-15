# Stock Analysis Skill for Claude Code

> Automated investment analysis for **China A-shares, US, and HK stocks** — structured data, annual report parsing, and multi-framework auditing.

**Live reports**: [MichaelFei87.github.io/Stock-Analysis-Reports](https://MichaelFei87.github.io/Stock-Analysis-Reports)

---

## What It Does

- Collects financial data via Tushare Pro (A/HK) and yfinance (US)
- Downloads and parses annual report PDFs for primary-source evidence
- Runs 12 auditing frameworks (Piotroski, Beneish, Altman, DuPont, Q4 wash, etc.) to surface red flags
- Generates a 13-section investment report with HTML visualization
- Optional `--monitor` mode to track changes against a prior baseline

---

## Quick Start

### 1. Install

```bash
curl -fsSL https://raw.githubusercontent.com/MichaelFei87/Stock-Analysis/main/install.sh | bash
```

### 2. Python dependencies

```bash
cd ~/.claude/skills/stock-analyze/scripts
pip3 install --user -r requirements.txt
```

### 3. Tushare token (required for A-shares / HK)

Register at [tushare.pro](https://tushare.pro/register) and export your token:

```bash
echo 'export TUSHARE_TOKEN="your_token_here"' >> ~/.zshrc && source ~/.zshrc
```

### 4. Tavily Search API key (strongly recommended)

The built-in WebSearch tool has poor coverage for Chinese financial sites and HK/US regulatory filings. **Tavily provides dramatically better search results** — in testing, it found Tencent's annual report PDF on HKEX and Tesla's 10-K on SEC.gov where WebSearch returned nothing.

- **Free tier**: 1,000 searches/month (enough for 100+ company analyses)
- **If you analyze HK or US stocks, this is essentially required**

Sign up at [tavily.com](https://tavily.com) and export your key:

```bash
echo 'export TAVILY_API_KEY="tvly-your_key_here"' >> ~/.zshrc && source ~/.zshrc
```

Without Tavily, the system falls back to WebSearch automatically — but expect significantly lower search hit rates for non-A-share markets.

### 5. Verify setup

```bash
cd ~/.claude/skills/stock-analyze
python3 -m scripts.check_env
```

### 6. Run

```
/stock-analyze 贵州茅台 600519.SH
/stock-analyze AAPL
/stock-analyze 实丰文化 --monitor
```
