"""yf_adapter.py — Backfill Tushare-format parquets from yfinance data.

When Tushare doesn't support a market (HK/US stocks), the core parquets
(income.parquet, balancesheet.parquet, cashflow.parquet, fina_indicator.parquet)
are empty. This adapter reads yfinance parquets (yf_income_annual.parquet, etc.)
and produces Tushare-compatible parquets so that data_snapshot.py works unchanged.

Only writes if the Tushare parquet is missing or empty (0 rows).
Unmappable fields are filled with NaN — data_snapshot.py already handles this.

CLI:
    python3 -m scripts.yf_adapter output/{company}/raw_data
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


# ---------- Field mappings: yfinance column → Tushare column ----------

INCOME_MAP = {
    "Total Revenue": "revenue",
    "Cost Of Revenue": "oper_cost",
    "Selling General And Administration": "sell_exp",
    "Research And Development": "rd_exp",
    "Interest Expense": "fin_exp",
    "Operating Income": "operate_profit",
    "Net Income": "n_income",
    "Basic EPS": "basic_eps",
    "Diluted EPS": "diluted_eps",
    "Gross Profit": "gross_profit",  # not in Tushare but useful
    "EBITDA": "ebitda",
    "Tax Provision": "income_tax",
    "Total Expenses": "total_cogs",
}

BALANCE_MAP = {
    "Total Assets": "total_assets",
    "Total Liabilities Net Minority Interest": "total_liab",
    "Common Stock Equity": "total_hldr_eqy_exc_min_int",
    "Total Equity Gross Minority Interest": "total_hldr_eqy_inc_min_int",
    "Minority Interest": "minority_int",
    "Cash And Cash Equivalents": "money_cap",
    "Accounts Receivable": "accounts_receiv",
    "Inventory": "inventories",
    "Net PPE": "fix_assets",
    "Construction In Progress": "cip",
    "Goodwill": "goodwill",
    "Other Intangible Assets": "intan_assets",
    "Current Debt": "st_borr",
    "Long Term Debt": "lt_borr",
    "Accounts Payable": "acct_payable",
    "Share Issued": "total_share",
    # Note: "Stockholders Equity" ≈ "Common Stock Equity" in yfinance; skip to avoid dup
    "Current Assets": "total_cur_assets",
    "Current Liabilities": "total_cur_liab",
    "Total Non Current Assets": "total_nca",
    "Total Non Current Liabilities Net Minority Interest": "total_ncl",
    "Net Debt": "netdebt",
    "Total Debt": "total_debt",
}

CASHFLOW_MAP = {
    "Operating Cash Flow": "n_cashflow_act",
    "Capital Expenditure": "c_pay_acq_const_fiolta",  # yfinance is negative
    "Free Cash Flow": "free_cashflow",
    "Investing Cash Flow": "n_cashflow_inv_act",
    "Financing Cash Flow": "n_cash_flows_fnc_act",
    "Cash Dividends Paid": "c_pay_dist_dpcp_int_exp",
    "Depreciation And Amortization": "depr_fa_coga_dpba",
    "Net Income": "net_profit",
}


def _read_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()


def _is_empty(path: Path) -> bool:
    """Check if a parquet file is missing or has 0 rows."""
    df = _read_safe(path)
    return df.empty


def _convert_period(df: pd.DataFrame) -> pd.DataFrame:
    """Convert yfinance 'period' column to Tushare 'end_date' (YYYYMMDD string)."""
    if "period" not in df.columns:
        return df
    df = df.copy()
    df["end_date"] = pd.to_datetime(df["period"]).dt.strftime("%Y%m%d")
    return df


def _apply_map(df: pd.DataFrame, field_map: dict[str, str]) -> pd.DataFrame:
    """Rename columns per field_map. Only maps columns that exist in df.
    If multiple source cols map to the same target, keep the first non-null."""
    rename = {src: dst for src, dst in field_map.items() if src in df.columns}
    # Detect duplicate targets
    seen: dict[str, str] = {}  # target → first source
    dedup_rename: dict[str, str] = {}
    drop_cols: list[str] = []
    for src, dst in rename.items():
        if dst in seen:
            drop_cols.append(src)  # drop duplicate source
        else:
            seen[dst] = src
            dedup_rename[src] = dst

    out = df.drop(columns=drop_cols, errors="ignore").rename(columns=dedup_rename)
    # Keep only mapped columns + end_date
    keep = [c for c in out.columns if c in seen or c == "end_date"]
    return out[keep] if keep else out


def _build_fina_indicator(raw_data_dir: Path) -> pd.DataFrame:
    """Derive fina_indicator fields from income + balance + cashflow yfinance data."""
    inc = _read_safe(raw_data_dir / "yf_income_annual.parquet")
    bs = _read_safe(raw_data_dir / "yf_balance_annual.parquet")
    cf = _read_safe(raw_data_dir / "yf_cashflow_annual.parquet")

    if inc.empty:
        return pd.DataFrame()

    inc = _convert_period(inc)
    bs = _convert_period(bs)
    cf = _convert_period(cf)

    rows = []
    for _, row in inc.iterrows():
        ed = row.get("end_date")
        if pd.isna(ed):
            continue

        r: dict = {"end_date": ed}

        revenue = row.get("Total Revenue")
        net_income = row.get("Net Income")
        gross_profit = row.get("Gross Profit")
        cogs = row.get("Cost Of Revenue")

        # EPS
        r["eps"] = row.get("Basic EPS")
        r["dt_eps"] = row.get("Diluted EPS")

        # Revenue per share & margins
        bs_row = bs[bs["end_date"] == ed].iloc[0] if not bs.empty and ed in bs["end_date"].values else None
        shares = bs_row.get("Share Issued") if bs_row is not None else None

        if revenue is not None and shares is not None and shares > 0:
            r["revenue_ps"] = revenue / shares

        if revenue is not None and revenue != 0:
            if gross_profit is not None:
                r["grossprofit_margin"] = (gross_profit / revenue) * 100
                r["gross_margin"] = r["grossprofit_margin"]  # alias for §2.4
            elif cogs is not None:
                r["grossprofit_margin"] = ((revenue - cogs) / revenue) * 100
                r["gross_margin"] = r["grossprofit_margin"]
            if net_income is not None:
                r["netprofit_margin"] = (net_income / revenue) * 100

        # ROE, ROA
        if bs_row is not None:
            equity = bs_row.get("Common Stock Equity")
            total_assets = bs_row.get("Total Assets")
            if equity is not None and equity != 0 and net_income is not None:
                r["roe"] = (net_income / equity) * 100
            if total_assets is not None and total_assets != 0 and net_income is not None:
                r["roa"] = (net_income / total_assets) * 100

            # Debt ratios
            total_liab = bs_row.get("Total Liabilities Net Minority Interest")
            if total_assets is not None and total_assets != 0 and total_liab is not None:
                r["debt_to_assets"] = (total_liab / total_assets) * 100
            if equity is not None and equity != 0 and total_liab is not None:
                r["debt_to_eqt"] = (total_liab / equity) * 100

            # Current/quick ratio
            cur_assets = bs_row.get("Current Assets")
            cur_liab = bs_row.get("Current Liabilities")
            inventory = bs_row.get("Inventory")
            if cur_liab is not None and cur_liab != 0:
                if cur_assets is not None:
                    r["current_ratio"] = cur_assets / cur_liab
                if cur_assets is not None and inventory is not None:
                    r["quick_ratio"] = (cur_assets - inventory) / cur_liab

            # Turnover ratios
            if revenue is not None and total_assets is not None and total_assets != 0:
                r["assets_turn"] = revenue / total_assets
            ar = bs_row.get("Accounts Receivable")
            if revenue is not None and ar is not None and ar != 0:
                r["ar_turn"] = revenue / ar
            if cogs is not None and inventory is not None and inventory != 0:
                r["inv_turn"] = cogs / inventory

            # BPS
            if shares is not None and shares != 0 and equity is not None:
                r["bps"] = equity / shares

            # Interest-bearing debt & net debt
            r["interestdebt"] = bs_row.get("Total Debt")
            r["netdebt"] = bs_row.get("Net Debt")

        # OCF per share & OCF/revenue
        cf_row = cf[cf["end_date"] == ed].iloc[0] if not cf.empty and ed in cf["end_date"].values else None
        if cf_row is not None:
            ocf = cf_row.get("Operating Cash Flow")
            if ocf is not None and shares is not None and shares > 0:
                r["ocfps"] = ocf / shares
            if ocf is not None and revenue is not None and revenue != 0:
                r["ocf_to_or"] = ocf / revenue

        rows.append(r)

    if not rows:
        return pd.DataFrame()

    fi = pd.DataFrame(rows)

    # Compute YoY for revenue and net income (need sorted by date)
    fi = fi.sort_values("end_date").reset_index(drop=True)
    if "eps" in fi.columns and len(fi) > 1:
        # Use revenue from income for YoY
        inc_sorted = inc.sort_values("end_date").reset_index(drop=True)
        rev_series = inc_sorted.set_index("end_date")["Total Revenue"] if "Total Revenue" in inc_sorted.columns else None
        ni_series = inc_sorted.set_index("end_date")["Net Income"] if "Net Income" in inc_sorted.columns else None

        tr_yoy = []
        np_yoy = []
        periods = fi["end_date"].tolist()
        for i, ed in enumerate(periods):
            if i == 0 or rev_series is None or ni_series is None:
                tr_yoy.append(None)
                np_yoy.append(None)
                continue
            prev_ed = periods[i - 1]
            try:
                curr_rev = rev_series.get(ed)
                prev_rev = rev_series.get(prev_ed)
                if curr_rev and prev_rev and prev_rev != 0:
                    tr_yoy.append((curr_rev / prev_rev - 1) * 100)
                else:
                    tr_yoy.append(None)
            except Exception:
                tr_yoy.append(None)
            try:
                curr_ni = ni_series.get(ed)
                prev_ni = ni_series.get(prev_ed)
                if curr_ni and prev_ni and prev_ni != 0:
                    np_yoy.append((curr_ni / prev_ni - 1) * 100)
                else:
                    np_yoy.append(None)
            except Exception:
                np_yoy.append(None)

        fi["tr_yoy"] = tr_yoy
        fi["netprofit_yoy"] = np_yoy

    return fi


def backfill_from_yfinance(raw_data_dir: str | Path) -> dict[str, str]:
    """Main entry point. Backfill empty Tushare parquets from yfinance data.

    Returns dict of {parquet_name: status} where status is 'backfilled' or 'skipped'.
    """
    d = Path(raw_data_dir)
    results: dict[str, str] = {}

    # --- income.parquet ---
    target = d / "income.parquet"
    if _is_empty(target):
        src = _read_safe(d / "yf_income_annual.parquet")
        if not src.empty:
            df = _convert_period(src)
            df = _apply_map(df, INCOME_MAP)
            # n_income_attr_p fallback: use n_income (yfinance Net Income is attributable for most)
            if "n_income" in df.columns and "n_income_attr_p" not in df.columns:
                df["n_income_attr_p"] = df["n_income"]
            df.to_parquet(target, index=False)
            results["income.parquet"] = f"backfilled ({len(df)} rows)"
        else:
            results["income.parquet"] = "skipped (no yfinance data)"
    else:
        results["income.parquet"] = "skipped (Tushare data exists)"

    # --- balancesheet.parquet ---
    target = d / "balancesheet.parquet"
    if _is_empty(target):
        src = _read_safe(d / "yf_balance_annual.parquet")
        if not src.empty:
            df = _convert_period(src)
            df = _apply_map(df, BALANCE_MAP)
            df.to_parquet(target, index=False)
            results["balancesheet.parquet"] = f"backfilled ({len(df)} rows)"
        else:
            results["balancesheet.parquet"] = "skipped (no yfinance data)"
    else:
        results["balancesheet.parquet"] = "skipped (Tushare data exists)"

    # --- cashflow.parquet ---
    target = d / "cashflow.parquet"
    if _is_empty(target):
        src = _read_safe(d / "yf_cashflow_annual.parquet")
        if not src.empty:
            df = _convert_period(src)
            df = _apply_map(df, CASHFLOW_MAP)
            # Capital expenditure: yfinance reports as negative, Tushare as positive
            if "c_pay_acq_const_fiolta" in df.columns:
                df["c_pay_acq_const_fiolta"] = df["c_pay_acq_const_fiolta"].abs()
            df.to_parquet(target, index=False)
            results["cashflow.parquet"] = f"backfilled ({len(df)} rows)"
        else:
            results["cashflow.parquet"] = "skipped (no yfinance data)"
    else:
        results["cashflow.parquet"] = "skipped (Tushare data exists)"

    # --- fina_indicator.parquet ---
    target = d / "fina_indicator.parquet"
    if _is_empty(target):
        fi = _build_fina_indicator(d)
        if not fi.empty:
            fi.to_parquet(target, index=False)
            results["fina_indicator.parquet"] = f"backfilled ({len(fi)} rows, derived)"
        else:
            results["fina_indicator.parquet"] = "skipped (no yfinance data)"
    else:
        results["fina_indicator.parquet"] = "skipped (Tushare data exists)"

    return results


def main():
    ap = argparse.ArgumentParser(
        description="Backfill Tushare-format parquets from yfinance data."
    )
    ap.add_argument("raw_data_dir", help="Path to output/{company}/raw_data")
    args = ap.parse_args()

    results = backfill_from_yfinance(args.raw_data_dir)
    for name, status in results.items():
        marker = "✅" if "backfilled" in status else "⏭️"
        print(f"{marker} {name}: {status}")

    backfilled = sum(1 for s in results.values() if "backfilled" in s)
    print(f"\nTotal: {backfilled}/{len(results)} parquets backfilled from yfinance")


if __name__ == "__main__":
    main()
