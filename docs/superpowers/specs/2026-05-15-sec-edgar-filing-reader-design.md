# SEC EDGAR Filing Reader — Design Spec

**Date**: 2026-05-15
**Status**: Draft
**Scope**: US equities only (A-share/HK paths unchanged)

## Problem

US stock analysis relies on two data paths that both have issues:

1. **Financial numbers**: `us_collector.py` uses yfinance — a third-party wrapper around SEC XBRL data. Adds an unnecessary dependency layer.
2. **Filing text (MD&A, Risk Factors, etc.)**: `pdf_reader.py` downloads SEC 10-K `.htm` files but applies A-share Chinese regex patterns to them. Result: 4/9 sections return garbage (TOC lines, XBRL tags, or <60 char stubs). The Figma (FIG) analysis on 2026-05-15 demonstrated this: `guidance=56 chars`, `mda=TOC page`, `risk_factors=TOC page`, `segment_info=XBRL tags`.

## Solution

Two new modules that directly use SEC EDGAR official APIs:

| New Module | Replaces | Data Source |
|---|---|---|
| `sec_collector.py` | `us_collector.py` (financial numbers) | SEC XBRL Company Facts API |
| `filing_reader.py` | `pdf_reader.py` (filing text, US path only) | SEC Filing HTML + DOM parsing |

yfinance retained only for market data (stock price, holders, dividends) that XBRL does not cover.

## Architecture

### Data Flow (Before vs After)

**Before:**
```
yfinance API → yf parquets → yf_adapter converts → Tushare-format parquets → data_snapshot/audit
SEC 10-K .htm → pdf_reader (CN regex) → garbage sections → Phase 2 has no useful text
```

**After:**
```
SEC XBRL JSON → sec_collector maps directly → Tushare-format parquets → data_snapshot/audit
SEC 10-K .htm → filing_reader (DOM parse by Item#) → clean sections → Phase 2 gets full text
yfinance → info/holders/history/dividends only (no financial statements)
```

### Module 1: `sec_collector.py`

#### Class: `SECCollector`

```python
class SECCollector:
    """XBRL + yfinance hybrid collector for US equities.
    
    XBRL handles: income, balance sheet, cash flow, financial indicators
    yfinance handles: stock price, holders, dividends, company info
    """

    def ticker_to_cik(self, ticker: str) -> str
    def get_company_facts(self, cik: str) -> dict
    def _xbrl_to_tushare_income(self, facts: dict, freq: str) -> pd.DataFrame
    def _xbrl_to_tushare_balance(self, facts: dict, freq: str) -> pd.DataFrame
    def _xbrl_to_tushare_cashflow(self, facts: dict, freq: str) -> pd.DataFrame
    def _xbrl_to_fina_indicator(self, facts: dict) -> pd.DataFrame
    def collect_all(self, code: str) -> dict[str, pd.DataFrame]
```

#### SEC EDGAR API Endpoints Used

| Endpoint | Purpose | Rate Limit |
|---|---|---|
| `https://www.sec.gov/files/company_tickers.json` | Ticker → CIK lookup | Cacheable (updates daily) |
| `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` | All historical GAAP financial data | 10 req/sec with User-Agent |
| `https://data.sec.gov/submissions/CIK{cik}.json` | Filing index (for filing_reader) | 10 req/sec with User-Agent |

SEC requires `User-Agent` header with contact info (e.g., `stock-analyze/1.0 user@example.com`). No API key needed.

#### XBRL Tag → Tushare Column Mapping

XBRL tags vary by company. Each Tushare column maps to an ordered priority list of candidate XBRL tags. First non-null match wins.

**Income statement (`XBRL_INCOME_MAP`):**

| Tushare Column | XBRL Candidate Tags (priority order) | Notes |
|---|---|---|
| `revenue` | `RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues`, `SalesRevenueNet` | SaaS companies often use the first |
| `oper_cost` | `CostOfRevenue`, `CostOfGoodsAndServicesSold` | |
| `sell_exp` | `SellingGeneralAndAdministrativeExpense`, `SellingAndMarketingExpense` | Some companies split SG&A |
| `rd_exp` | `ResearchAndDevelopmentExpense` | |
| `fin_exp` | `InterestExpense`, `InterestExpenseDebt` | |
| `operate_profit` | `OperatingIncomeLoss` | |
| `n_income` | `NetIncomeLoss` | |
| `basic_eps` | `EarningsPerShareBasic` | |
| `diluted_eps` | `EarningsPerShareDiluted` | |
| `income_tax` | `IncomeTaxExpenseBenefit` | |
| `ebitda` | `EBITDA` | Rare in XBRL; may need derivation |
| `gross_profit` | `GrossProfit` | |

**Balance sheet (`XBRL_BALANCE_MAP`):**

| Tushare Column | XBRL Candidate Tags | Notes |
|---|---|---|
| `total_assets` | `Assets` | |
| `total_liab` | `Liabilities` | |
| `total_hldr_eqy_exc_min_int` | `StockholdersEquity` | |
| `total_hldr_eqy_inc_min_int` | `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` | |
| `money_cap` | `CashAndCashEquivalentsAtCarryingValue`, `Cash` | |
| `accounts_receiv` | `AccountsReceivableNetCurrent` | |
| `total_cur_assets` | `AssetsCurrent` | |
| `total_cur_liab` | `LiabilitiesCurrent` | |
| `lt_borr` | `LongTermDebt`, `LongTermDebtNoncurrent` | |
| `st_borr` | `ShortTermBorrowings`, `DebtCurrent` | |
| `goodwill` | `Goodwill` | |
| `fix_assets` | `PropertyPlantAndEquipmentNet` | |
| `total_share` | `CommonStockSharesOutstanding` | |

**Cash flow (`XBRL_CASHFLOW_MAP`):**

| Tushare Column | XBRL Candidate Tags | Notes |
|---|---|---|
| `n_cashflow_act` | `NetCashProvidedByOperatingActivities` | |
| `n_cashflow_inv_act` | `NetCashProvidedByInvestingActivities` | |
| `n_cash_flows_fnc_act` | `NetCashProvidedByFinancingActivities` | |
| `c_pay_acq_const_fiolta` | `PaymentsToAcquirePropertyPlantAndEquipment` | CapEx (positive in XBRL, negate) |
| `depr_fa_coga_dpba` | `DepreciationDepletionAndAmortization` | |
| `net_profit` | `NetIncomeLoss` | Duplicate from income, for CF context |
| `free_cashflow` | (derived: OCF - CapEx) | Not a standard XBRL tag |

#### `collect_all()` Output

Returns `dict[str, pd.DataFrame]` — same keys and Tushare column names as `USCollector.collect_all()` + `yf_adapter.backfill_from_yfinance()` combined output. This means:

- `save_bundle()` works unchanged
- `data_snapshot.py` works unchanged
- `financial_audit.py` works unchanged
- `yf_adapter.py` is NOT called when XBRL succeeds

**Bundle keys:**

| Key | Source | Format |
|---|---|---|
| `income_annual` | XBRL | Tushare columns + `end_date` |
| `income_quarterly` | XBRL | Tushare columns + `end_date` |
| `balance_annual` | XBRL | Tushare columns + `end_date` |
| `balance_quarterly` | XBRL | Tushare columns + `end_date` |
| `cashflow_annual` | XBRL | Tushare columns + `end_date` |
| `cashflow_quarterly` | XBRL | Tushare columns + `end_date` |
| `fina_indicator` | XBRL (derived) | Tushare columns + `end_date` |
| `info` | yfinance | Single-row metadata |
| `major_holders` | yfinance | Holder percentages |
| `institutional_holders` | yfinance | Top institutions |
| `history_5y` | yfinance | OHLCV daily |
| `dividends` | yfinance | Date + amount |

#### XBRL Parsing Logic

The Company Facts JSON structure:
```json
{
  "cik": 1234,
  "entityName": "FIGMA INC",
  "facts": {
    "us-gaap": {
      "Revenues": {
        "units": {
          "USD": [
            {"end": "2024-12-31", "val": 100000000, "form": "10-K", "fy": 2024, "fp": "FY"},
            {"end": "2024-09-30", "val": 75000000, "form": "10-Q", "fy": 2024, "fp": "Q3"},
            ...
          ]
        }
      },
      "NetIncomeLoss": { ... },
      ...
    }
  }
}
```

Parsing rules:
1. For annual data: filter entries where `form == "10-K"` and `fp == "FY"`
2. For quarterly data: filter where `form == "10-Q"` and `fp in ("Q1", "Q2", "Q3")`
3. Deduplicate by `end` date (keep latest filing if amended)
4. Convert `end` → `end_date` (YYYYMMDD string) for Tushare compatibility
5. Handle sign conventions: CapEx in XBRL is positive, Tushare expects negative → negate

### Module 2: `filing_reader.py`

#### Class: `FilingReader`

```python
class FilingReader:
    """SEC 10-K/10-Q HTML filing reader.
    
    Replaces pdf_reader.py for US stocks. Parses SEC HTML filings
    by Item number (Regulation S-K structure) using DOM traversal.
    """

    def get_latest_filings(self, cik: str, form_type: str = "10-K", count: int = 1) -> list[dict]
    def download_filing(self, url: str, save_path: Path) -> Path
    def parse_sections(self, html_path: Path) -> dict[str, str]
    def extract_tables(self, html_path: Path, section: str) -> list[pd.DataFrame]
```

#### Filing Discovery: `get_latest_filings()`

Uses `https://data.sec.gov/submissions/CIK{cik}.json`:
1. Filter `recentFilings` by `form` field matching `form_type`
2. Extract `accessionNumber`, `filingDate`, `primaryDocument`
3. Construct download URL: `https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primaryDocument}`
4. Return list of `{accession, date, primary_document, url}`

#### HTML Section Parsing: `parse_sections()`

10-K filings follow SEC Regulation S-K with standardized Item numbers. Parsing strategy:

1. **Load HTML** with BeautifulSoup + lxml parser
2. **Find Item anchors** — SEC filings use several patterns:
   - `<a name="item1a">` or `<a id="item1a">`
   - `<b>Item 1A</b>` or `<font><b>ITEM 1A.</b></font>`
   - Table of contents links pointing to `#item7`
   - Inline XBRL wrapper: `<ix:nonNumeric>` around section text
3. **Build anchor map** — regex `r'item\s*(\d+[a-z]?)'` (case-insensitive) on text content of heading-like elements (`<b>`, `<h1>`-`<h4>`, `<p>` with bold/large font)
4. **Slice between anchors** — extract all text between Item N start and Item N+1 start
5. **Clean text** — strip HTML tags, collapse whitespace, remove page headers/footers
6. **Map to standard keys** — return dict with pdf_reader-compatible keys:

| 10-K Item | Section Key | pdf_reader Equivalent |
|---|---|---|
| Item 1 | `business` | (new — pdf_reader didn't extract this) |
| Item 1A | `risk_factors` | `risks` |
| Item 7 | `mda` | `mda` |
| Item 7A | `market_risk` | (new) |
| Item 8 | `financial_statements` | `main_financial_data` (partial overlap) |

| 10-Q Item | Section Key | Notes |
|---|---|---|
| Item 2 | `mda` | Same key as 10-K Item 7 |
| Item 1A (if present) | `risk_factors` | Not all 10-Qs have this |

Additional keys extracted from financial statement notes (if parseable):
- `segment_info` — from Note on Segment Reporting
- `sbc_detail` — from Note on Stock-Based Compensation (critical for SaaS companies like Figma)

#### File Type Router

The `data-collector` agent uses file extension to choose parser:

```
.pdf          → pdf_reader.extract_sections()
.htm / .html  → filing_reader.parse_sections()
```

This also fixes already-downloaded `.htm` files that previously failed with `pdf_reader`.

### Integration Changes

#### Files Modified

| File | Change | Scope |
|---|---|---|
| `agents/data-collector.md` | Step 1: add SEC collector path for US stocks. Step 3: route `.htm` to `filing_reader` | Prompt change |
| `scripts/requirements.txt` | Add `beautifulsoup4`, `lxml` | Dependency |
| `scripts/__init__.py` | (no change — new modules auto-discoverable) | — |

#### Files NOT Modified

| File | Why |
|---|---|
| `us_collector.py` | Retained as yfinance fallback |
| `yf_adapter.py` | Retained; only triggered if XBRL fails |
| `pdf_reader.py` | A-share / HK paths unchanged |
| `data_snapshot.py` | Reads Tushare-format parquets — XBRL writes same format |
| `financial_audit.py` | Same input format |
| `data_cache.py` | Used by both new and old collectors |
| Phase 3 agents | Read `data_snapshot.md` + `phase2-documents.md` — upstream format unchanged |
| Phase 6 reviewers | No data layer dependency |

### Fallback Strategy

```
Tier 1: sec_collector (XBRL) for financials + filing_reader (HTML) for text
  ↓ XBRL API fails or returns empty
Tier 2: us_collector (yfinance) + yf_adapter for financials
  ↓ yfinance also fails  
Tier 3: Phase 1 reports "部分降级", analysis continues with available data

Filing text fallback:
Tier 1: filing_reader.parse_sections() on .htm
  ↓ HTML download fails
Tier 2: pdf_reader.extract_sections() if a .pdf exists
  ↓ both fail
Tier 3: No filing text — Phase 2 works from data_snapshot only
```

`data-collector` agent sets `phase1-data.md` verdict:
- All XBRL + HTML succeed → `**判定**: PASS`
- XBRL fails, yfinance fallback works → `**判定**: 部分降级(XBRL不可用,yfinance替代)`
- Filing HTML partial extraction → `**判定**: 部分降级(filing解析不完整,N/M sections)`

### SEC API Compliance

- **User-Agent**: Required. Format: `stock-analyze/1.0 (contact@example.com)`. Configurable via `config.py`.
- **Rate limit**: 10 requests/second. Reuse existing `data_cache.py` throttle mechanism.
- **No API key**: SEC EDGAR is fully public.
- **Caching**: Company Facts JSON and Filing HTML cached via `data_cache.py` with 7-day TTL (same as yfinance).

### New Dependencies

| Package | Purpose | Size |
|---|---|---|
| `beautifulsoup4` | HTML DOM parsing | ~500KB |
| `lxml` | Fast parser backend for BS4 | ~10MB (C extension) |

No new API keys or tokens required.

### Implementation Order

1. `sec_collector.py` — `ticker_to_cik()` + `get_company_facts()` + XBRL→Tushare mappers + `collect_all()`
2. `filing_reader.py` — `get_latest_filings()` + `download_filing()` + `parse_sections()`
3. `agents/data-collector.md` — update prompt for US market path
4. Integration test: run against FIG (Figma) and AAPL to verify output parity with yfinance

### Success Criteria

1. `sec_collector.collect_all("FIG")` returns all 12 bundle keys with non-empty DataFrames for financial statements
2. `data_snapshot.py` produces identical or better coverage percentage vs yfinance path
3. `filing_reader.parse_sections()` extracts `mda` and `risk_factors` with >1000 chars each from Figma 10-K
4. `financial_audit.py` runs without error on XBRL-sourced parquets
5. Full pipeline test: `/stock-analyze 美股 FIG` completes with Phase 1 verdict PASS (not 部分降级)
