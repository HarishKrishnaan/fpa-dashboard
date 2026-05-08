"""
Core FP&A calculation engine.

This module intentionally keeps finance logic separate
from the Streamlit UI to make it easier to test.

Finance convention used in this project:
- Input files should enter Revenue and Expense amounts as positive numbers.
- The P&L engine decides whether to add or subtract a section.
- Example: Revenue = 100000, COGS = 40000, Gross Profit = 60000.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd


VALID_SECTIONS = {
    "Revenue",
    "COGS",
    "Operating Expense",
    "Other Income",
    "Other Expense",
    "Tax",
}

SECTION_ALIASES = {
    "sales": "Revenue",
    "income": "Revenue",
    "revenue": "Revenue",
    "cogs": "COGS",
    "cost of goods sold": "COGS",
    "cost of revenue": "COGS",
    "opex": "Operating Expense",
    "operating expense": "Operating Expense",
    "operating expenses": "Operating Expense",
    "sg&a": "Operating Expense",
    "sga": "Operating Expense",
    "other income": "Other Income",
    "interest income": "Other Income",
    "other expense": "Other Expense",
    "interest expense": "Other Expense",
    "tax": "Tax",
    "taxes": "Tax",
    "income tax": "Tax",
}

PNL_LINE_ORDER = [
    "Revenue",
    "COGS",
    "Gross Profit",
    "Operating Expense",
    "Operating Income",
    "Other Income",
    "Other Expense",
    "Pre-Tax Income",
    "Tax",
    "Net Income",
]


@dataclass
class ForecastAssumptions:
    """User-controlled assumptions for the rolling forecast."""

    monthly_revenue_growth: float = 0.02
    cogs_percent_of_revenue: float | None = None
    monthly_opex_growth: float = 0.01
    monthly_other_expense_growth: float = 0.00
    effective_tax_rate: float = 0.21
    monthly_new_headcount_cost: float = 0.0


@dataclass
class ScenarioAssumptions:
    """Three-scenario wrapper for base, upside, and downside cases."""

    base: ForecastAssumptions
    upside: ForecastAssumptions
    downside: ForecastAssumptions


def normalize_section(value: object) -> str:
    """Map messy finance section names into a clean set used by the model."""
    if pd.isna(value):
        return "Operating Expense"
    raw = str(value).strip()
    lowered = raw.lower()
    return SECTION_ALIASES.get(lowered, raw.title() if raw.title() in VALID_SECTIONS else raw)


def clean_financial_df(df: pd.DataFrame, scenario: str) -> pd.DataFrame:
    """
    Validate and standardize an actuals, budget, or forecast dataframe.

    Required columns after normalization:
    - month: month or date of financial activity
    - account: account or line item name
    - section: Revenue, COGS, Operating Expense, Other Income, Other Expense, or Tax
    - amount: positive dollar amount
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["month", "account", "section", "amount", "department", "scenario"])

    # Tolerate common column names recruiters or finance teams might use.
    rename_map = {}
    for col in df.columns:
        key = str(col).strip().lower().replace(" ", "_")
        if key in {"date", "period", "month", "fiscal_month"}:
            rename_map[col] = "month"
        elif key in {"account", "line_item", "gl_account", "account_name", "pnl_line"}:
            rename_map[col] = "account"
        elif key in {"section", "category", "statement_section", "type"}:
            rename_map[col] = "section"
        elif key in {"amount", "value", "actual", "budget", "forecast"}:
            rename_map[col] = "amount"
        elif key in {"department", "dept", "cost_center"}:
            rename_map[col] = "department"

    df = df.rename(columns=rename_map).copy()
    missing = {"month", "account", "section", "amount"} - set(df.columns)
    if missing:
        raise ValueError(
            f"Missing required column(s): {', '.join(sorted(missing))}. "
            "Expected month, account, section, and amount."
        )

    df["month"] = pd.to_datetime(df["month"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    if df["month"].isna().any():
        bad_rows = df[df["month"].isna()].head(5).index.tolist()
        raise ValueError(f"Could not parse month/date values in rows: {bad_rows}")

    df["account"] = df["account"].astype(str).str.strip()
    df["section"] = df["section"].apply(normalize_section)
    invalid_sections = sorted(set(df["section"]) - VALID_SECTIONS)
    if invalid_sections:
        raise ValueError(
            "Invalid section value(s): "
            + ", ".join(invalid_sections)
            + ". Use Revenue, COGS, Operating Expense, Other Income, Other Expense, or Tax."
        )

    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    if df["amount"].isna().any():
        bad_rows = df[df["amount"].isna()].head(5).index.tolist()
        raise ValueError(f"Amount column contains non-numeric values in rows: {bad_rows}")

    # Finance planning models typically use positive expenses and subtract by section.
    # If a user uploads negative expenses, convert to absolute value to avoid double subtraction.
    df["amount"] = df["amount"].abs()

    if "department" not in df.columns:
        df["department"] = "Company"
    df["department"] = df["department"].fillna("Company").astype(str).str.strip()
    df["scenario"] = scenario

    return df[["month", "account", "section", "amount", "department", "scenario"]]


def monthly_account_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize a scenario at month/account/section level."""
    if df.empty:
        return df.copy()
    return (
        df.groupby(["month", "section", "account", "department", "scenario"], as_index=False)["amount"]
        .sum()
        .sort_values(["month", "section", "account"])
    )


def _monthly_section_totals(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["month", "scenario", "section", "amount"])
    return df.groupby(["month", "scenario", "section"], as_index=False)["amount"].sum()


def build_pnl(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a management-style P&L report by month and scenario.

    Output columns:
    - scenario
    - pnl_line
    - month
    - amount
    """
    if df.empty:
        return pd.DataFrame(columns=["scenario", "pnl_line", "month", "amount"])

    section_totals = _monthly_section_totals(df)
    pivot = section_totals.pivot_table(
        index=["scenario", "month"], columns="section", values="amount", aggfunc="sum", fill_value=0.0
    ).reset_index()

    for section in VALID_SECTIONS:
        if section not in pivot.columns:
            pivot[section] = 0.0

    # P&L calculations.
    pivot["Gross Profit"] = pivot["Revenue"] - pivot["COGS"]
    pivot["Operating Income"] = pivot["Gross Profit"] - pivot["Operating Expense"]
    pivot["Pre-Tax Income"] = pivot["Operating Income"] + pivot["Other Income"] - pivot["Other Expense"]
    pivot["Net Income"] = pivot["Pre-Tax Income"] - pivot["Tax"]

    lines = []
    for line in PNL_LINE_ORDER:
        temp = pivot[["scenario", "month", line]].copy()
        temp = temp.rename(columns={line: "amount"})
        temp["pnl_line"] = line
        lines.append(temp[["scenario", "pnl_line", "month", "amount"]])

    pnl = pd.concat(lines, ignore_index=True)
    pnl["pnl_line"] = pd.Categorical(pnl["pnl_line"], PNL_LINE_ORDER, ordered=True)
    return pnl.sort_values(["scenario", "pnl_line", "month"])


def pnl_pivot_for_display(pnl: pd.DataFrame, scenario: str) -> pd.DataFrame:
    """Return a wide P&L table with months as columns for Streamlit display."""
    if pnl.empty:
        return pd.DataFrame()
    temp = pnl[pnl["scenario"] == scenario].copy()
    if temp.empty:
        return pd.DataFrame()
    temp["month"] = temp["month"].dt.strftime("%Y-%m")
    wide = temp.pivot_table(index="pnl_line", columns="month", values="amount", aggfunc="sum", fill_value=0.0, observed=False)
    wide = wide.reindex(PNL_LINE_ORDER)
    wide["YTD / Total"] = wide.sum(axis=1)
    return wide.reset_index().rename(columns={"pnl_line": "P&L Line"})


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator not in (0, 0.0, None) else 0.0


def calculate_kpis(pnl: pd.DataFrame, scenario: str, months: Iterable[pd.Timestamp] | None = None) -> Dict[str, float]:
    """Calculate common FP&A KPIs from the P&L."""
    if pnl.empty:
        return {
            "Revenue": 0.0,
            "Gross Profit": 0.0,
            "Gross Margin": 0.0,
            "Operating Income": 0.0,
            "Operating Margin": 0.0,
            "Net Income": 0.0,
            "Net Margin": 0.0,
        }

    temp = pnl[pnl["scenario"] == scenario].copy()
    if months is not None:
        months = set(pd.to_datetime(list(months)).to_period("M").to_timestamp())
        temp = temp[temp["month"].isin(months)]

    totals = temp.groupby("pnl_line", observed=False)["amount"].sum().to_dict()
    revenue = float(totals.get("Revenue", 0.0))
    gross_profit = float(totals.get("Gross Profit", 0.0))
    operating_income = float(totals.get("Operating Income", 0.0))
    net_income = float(totals.get("Net Income", 0.0))

    return {
        "Revenue": revenue,
        "Gross Profit": gross_profit,
        "Gross Margin": _safe_ratio(gross_profit, revenue),
        "Operating Income": operating_income,
        "Operating Margin": _safe_ratio(operating_income, revenue),
        "Net Income": net_income,
        "Net Margin": _safe_ratio(net_income, revenue),
    }


def latest_actual_month(actuals: pd.DataFrame) -> pd.Timestamp | None:
    """Find the last month with actuals uploaded."""
    if actuals.empty:
        return None
    return pd.to_datetime(actuals["month"]).max().to_period("M").to_timestamp()


def _recent_account_base(actuals: pd.DataFrame, lookback_months: int = 3) -> pd.DataFrame:
    """Create a recent run-rate by account based on the latest actual months."""
    if actuals.empty:
        return pd.DataFrame(columns=["section", "account", "department", "amount"])
    last_month = latest_actual_month(actuals)
    cutoff = last_month - pd.DateOffset(months=lookback_months - 1)
    recent = actuals[(actuals["month"] >= cutoff) & (actuals["month"] <= last_month)]
    return recent.groupby(["section", "account", "department"], as_index=False)["amount"].mean()


def _section_total(df: pd.DataFrame, section: str) -> float:
    return float(df.loc[df["section"] == section, "amount"].sum()) if not df.empty else 0.0


def generate_forecast(
    actuals: pd.DataFrame,
    budget: pd.DataFrame,
    assumptions: ForecastAssumptions,
    fiscal_year: int,
    scenario_name: str = "Forecast",
) -> pd.DataFrame:
    """
    Generate a driver-based forecast for future months in the fiscal year.

    The model uses the latest actual run-rate when possible and falls back to
    budget. Revenue is forecast using monthly growth. COGS follows a COGS % of
    revenue. Operating expenses grow by a monthly OpEx assumption, and payroll
    can be increased by an explicit monthly new-headcount cost.
    """
    if budget.empty and actuals.empty:
        return pd.DataFrame(columns=["month", "account", "section", "amount", "department", "scenario"])

    actual_last = latest_actual_month(actuals)
    if actual_last is None:
        start_month = pd.Timestamp(fiscal_year, 1, 1)
    else:
        start_month = actual_last + pd.DateOffset(months=1)

    year_end = pd.Timestamp(fiscal_year, 12, 1)
    if start_month > year_end:
        return pd.DataFrame(columns=["month", "account", "section", "amount", "department", "scenario"])

    future_months = pd.date_range(start_month, year_end, freq="MS")

    recent_base = _recent_account_base(actuals)
    if recent_base.empty:
        # If no actuals exist, start from average budget by account.
        recent_base = budget.groupby(["section", "account", "department"], as_index=False)["amount"].mean()

    recent_revenue = _section_total(recent_base, "Revenue")
    recent_cogs = _section_total(recent_base, "COGS")
    cogs_pct = assumptions.cogs_percent_of_revenue
    if cogs_pct is None:
        cogs_pct = _safe_ratio(recent_cogs, recent_revenue)

    # Mix tables let us distribute total forecast values back into accounts.
    def mix(section: str) -> pd.DataFrame:
        s = recent_base[recent_base["section"] == section].copy()
        total = s["amount"].sum()
        if s.empty or total == 0:
            fallback = budget[budget["section"] == section].groupby(["section", "account", "department"], as_index=False)["amount"].mean()
            total = fallback["amount"].sum()
            s = fallback
        if s.empty or total == 0:
            return pd.DataFrame(columns=["section", "account", "department", "mix"])
        s["mix"] = s["amount"] / total
        return s[["section", "account", "department", "mix"]]

    revenue_mix = mix("Revenue")
    cogs_mix = mix("COGS")
    opex_base = recent_base[recent_base["section"] == "Operating Expense"].copy()
    other_income_base = recent_base[recent_base["section"] == "Other Income"].copy()
    other_expense_base = recent_base[recent_base["section"] == "Other Expense"].copy()

    rows: List[Dict[str, object]] = []
    for idx, month in enumerate(future_months, start=1):
        revenue_total = recent_revenue * ((1 + assumptions.monthly_revenue_growth) ** idx)
        cogs_total = revenue_total * cogs_pct

        # Revenue account allocation.
        for _, r in revenue_mix.iterrows():
            rows.append(
                {
                    "month": month,
                    "section": "Revenue",
                    "account": r["account"],
                    "department": r["department"],
                    "amount": revenue_total * r["mix"],
                    "scenario": scenario_name,
                }
            )

        # COGS allocation.
        for _, r in cogs_mix.iterrows():
            rows.append(
                {
                    "month": month,
                    "section": "COGS",
                    "account": r["account"],
                    "department": r["department"],
                    "amount": cogs_total * r["mix"],
                    "scenario": scenario_name,
                }
            )

        # Operating expenses are projected from account-level run-rate.
        for _, r in opex_base.iterrows():
            amount = float(r["amount"]) * ((1 + assumptions.monthly_opex_growth) ** idx)
            # Assign additional headcount cost to payroll-like accounts.
            if any(term in str(r["account"]).lower() for term in ["salary", "salaries", "payroll", "wages"]):
                amount += assumptions.monthly_new_headcount_cost * idx
            rows.append(
                {
                    "month": month,
                    "section": "Operating Expense",
                    "account": r["account"],
                    "department": r["department"],
                    "amount": amount,
                    "scenario": scenario_name,
                }
            )

        for _, r in other_income_base.iterrows():
            rows.append(
                {
                    "month": month,
                    "section": "Other Income",
                    "account": r["account"],
                    "department": r["department"],
                    "amount": float(r["amount"]),
                    "scenario": scenario_name,
                }
            )

        for _, r in other_expense_base.iterrows():
            rows.append(
                {
                    "month": month,
                    "section": "Other Expense",
                    "account": r["account"],
                    "department": r["department"],
                    "amount": float(r["amount"]) * ((1 + assumptions.monthly_other_expense_growth) ** idx),
                    "scenario": scenario_name,
                }
            )

        # Taxes are modeled directly from pre-tax income, not copied from recent base.
        pre_tax = revenue_total - cogs_total - sum(
            row["amount"]
            for row in rows
            if row["month"] == month and row["section"] == "Operating Expense"
        )
        estimated_tax = max(pre_tax, 0.0) * assumptions.effective_tax_rate
        rows.append(
            {
                "month": month,
                "section": "Tax",
                "account": "Income Tax Expense",
                "department": "Finance",
                "amount": estimated_tax,
                "scenario": scenario_name,
            }
        )

    return pd.DataFrame(rows)


def build_scenarios(
    actuals: pd.DataFrame,
    budget: pd.DataFrame,
    fiscal_year: int,
    assumptions: ScenarioAssumptions,
) -> pd.DataFrame:
    """Generate base, upside, and downside forecasts."""
    frames = [
        generate_forecast(actuals, budget, assumptions.base, fiscal_year, "Base Forecast"),
        generate_forecast(actuals, budget, assumptions.upside, fiscal_year, "Upside Forecast"),
        generate_forecast(actuals, budget, assumptions.downside, fiscal_year, "Downside Forecast"),
    ]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def combined_actual_budget_forecast(actuals: pd.DataFrame, budget: pd.DataFrame, forecast: pd.DataFrame) -> pd.DataFrame:
    """Combine all scenarios into one fact table."""
    frames = [df for df in [actuals, budget, forecast] if df is not None and not df.empty]
    if not frames:
        return pd.DataFrame(columns=["month", "account", "section", "amount", "department", "scenario"])
    return pd.concat(frames, ignore_index=True)


def variance_analysis(actuals: pd.DataFrame, budget: pd.DataFrame) -> pd.DataFrame:
    """
    Compare actuals against budget by account for overlapping months only.

    Positive variance is favorable for revenue and unfavorable for expenses by
    raw math, so we also calculate a finance-aware Favorable/(Unfavorable) flag.
    """
    if actuals.empty or budget.empty:
        return pd.DataFrame(
            columns=[
                "section",
                "account",
                "actual",
                "budget",
                "variance",
                "variance_pct",
                "favorability",
                "commentary",
            ]
        )

    actual_months = set(actuals["month"].unique())
    budget_overlap = budget[budget["month"].isin(actual_months)]

    actual_sum = actuals.groupby(["section", "account"], as_index=False)["amount"].sum().rename(columns={"amount": "actual"})
    budget_sum = (
        budget_overlap.groupby(["section", "account"], as_index=False)["amount"].sum().rename(columns={"amount": "budget"})
    )
    merged = pd.merge(actual_sum, budget_sum, on=["section", "account"], how="outer").fillna(0.0)
    merged["variance"] = merged["actual"] - merged["budget"]
    merged["variance_pct"] = np.where(merged["budget"] != 0, merged["variance"] / merged["budget"], 0.0)

    def favorability(row: pd.Series) -> str:
        section = row["section"]
        var = row["variance"]
        if abs(var) < 1e-9:
            return "On Plan"
        if section in {"Revenue", "Other Income"}:
            return "Favorable" if var > 0 else "Unfavorable"
        return "Unfavorable" if var > 0 else "Favorable"

    def commentary(row: pd.Series) -> str:
        var_abs = abs(float(row["variance"]))
        pct = abs(float(row["variance_pct"]))
        direction = "above" if row["variance"] > 0 else "below"
        if row["favorability"] == "On Plan":
            return f"{row['account']} was in line with budget."
        return (
            f"{row['account']} was ${var_abs:,.0f} {direction} budget "
            f"({pct:.1%}), which is {row['favorability'].lower()} for {row['section'].lower()}."
        )

    merged["favorability"] = merged.apply(favorability, axis=1)
    merged["commentary"] = merged.apply(commentary, axis=1)
    return merged.sort_values("variance", key=lambda s: s.abs(), ascending=False)


def clean_balance_sheet_df(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and standardize a balance sheet upload."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["as_of_date", "section", "line_item", "amount"])

    rename_map = {}
    for col in df.columns:
        key = str(col).strip().lower().replace(" ", "_")
        if key in {"as_of_date", "date", "period", "month"}:
            rename_map[col] = "as_of_date"
        elif key in {"section", "category", "type"}:
            rename_map[col] = "section"
        elif key in {"line_item", "account", "item", "balance_sheet_line"}:
            rename_map[col] = "line_item"
        elif key in {"amount", "value", "balance"}:
            rename_map[col] = "amount"

    df = df.rename(columns=rename_map).copy()
    missing = {"section", "line_item", "amount"} - set(df.columns)
    if missing:
        raise ValueError(
            f"Balance sheet is missing required column(s): {', '.join(sorted(missing))}. "
            "Expected section, line_item, and amount."
        )
    if "as_of_date" not in df.columns:
        df["as_of_date"] = pd.Timestamp.today().normalize()
    else:
        df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce").fillna(pd.Timestamp.today().normalize())

    df["section"] = df["section"].astype(str).str.strip().str.title()
    df["line_item"] = df["line_item"].astype(str).str.strip()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    return df[["as_of_date", "section", "line_item", "amount"]]


def balance_sheet_summary(balance_sheet: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Summarize balance sheet and calculate liquidity/leverage KPIs."""
    if balance_sheet.empty:
        return pd.DataFrame(), {
            "Total Assets": 0.0,
            "Total Liabilities": 0.0,
            "Total Equity": 0.0,
            "Balance Check": 0.0,
            "Current Ratio": 0.0,
            "Debt-to-Equity": 0.0,
        }

    summary = balance_sheet.groupby("section", as_index=False)["amount"].sum()
    section_totals = summary.set_index("section")["amount"].to_dict()
    current_assets = section_totals.get("Current Asset", 0.0) + section_totals.get("Current Assets", 0.0)
    noncurrent_assets = section_totals.get("Noncurrent Asset", 0.0) + section_totals.get("Noncurrent Assets", 0.0)
    current_liabilities = section_totals.get("Current Liability", 0.0) + section_totals.get("Current Liabilities", 0.0)
    noncurrent_liabilities = section_totals.get("Noncurrent Liability", 0.0) + section_totals.get("Noncurrent Liabilities", 0.0)
    equity = section_totals.get("Equity", 0.0)

    total_assets = current_assets + noncurrent_assets
    total_liabilities = current_liabilities + noncurrent_liabilities
    balance_check = total_assets - total_liabilities - equity

    kpis = {
        "Total Assets": total_assets,
        "Total Liabilities": total_liabilities,
        "Total Equity": equity,
        "Balance Check": balance_check,
        "Current Ratio": _safe_ratio(current_assets, current_liabilities),
        "Debt-to-Equity": _safe_ratio(total_liabilities, equity),
    }
    return summary, kpis


def derive_simple_balance_sheet(actuals: pd.DataFrame, starting_cash: float = 750_000.0) -> pd.DataFrame:
    """
    Generate a simplified balance sheet when the user has not uploaded one.

    This is not meant to replace a real accounting system. It exists so the demo
    can show how P&L activity flows into cash/equity concepts.
    """
    pnl = build_pnl(actuals)
    actual_kpis = calculate_kpis(pnl, "Actual")
    net_income = actual_kpis["Net Income"]
    revenue = actual_kpis["Revenue"]
    opex = actuals.loc[actuals["section"].isin(["COGS", "Operating Expense", "Other Expense", "Tax"]), "amount"].sum()

    # Very simplified working capital assumptions.
    accounts_receivable = revenue * 0.15
    accounts_payable = opex * 0.10
    cash = starting_cash + net_income - accounts_receivable + accounts_payable
    fixed_assets = 500_000.0
    debt = 350_000.0
    equity = cash + accounts_receivable + fixed_assets - accounts_payable - debt

    as_of = actuals["month"].max() if not actuals.empty else pd.Timestamp.today().normalize()
    data = [
        {"as_of_date": as_of, "section": "Current Asset", "line_item": "Cash", "amount": cash},
        {"as_of_date": as_of, "section": "Current Asset", "line_item": "Accounts Receivable", "amount": accounts_receivable},
        {"as_of_date": as_of, "section": "Noncurrent Asset", "line_item": "Fixed Assets", "amount": fixed_assets},
        {"as_of_date": as_of, "section": "Current Liability", "line_item": "Accounts Payable", "amount": accounts_payable},
        {"as_of_date": as_of, "section": "Noncurrent Liability", "line_item": "Debt", "amount": debt},
        {"as_of_date": as_of, "section": "Equity", "line_item": "Owner Equity + Retained Earnings", "amount": equity},
    ]
    return pd.DataFrame(data)
