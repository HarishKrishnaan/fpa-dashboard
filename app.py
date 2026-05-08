"""
FP&A Forecasting and Variance Analysis Dashboard

Run locally:
    streamlit run app.py

This app demonstrates a realistic corporate finance / FP&A workflow:
1. Load actual financial results.
2. Load or edit the annual budget.
3. Generate base, upside, and downside forecasts.
4. Build P&L reports.
5. Analyze budget vs actual variances.
6. Show a balance sheet snapshot.
7. Export a management-ready Excel reporting package.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src.data_loader import dollars, percent, read_table
from src.excel_exporter import create_excel_report
from src.finance_engine import (
    ForecastAssumptions,
    ScenarioAssumptions,
    VALID_SECTIONS,
    balance_sheet_summary,
    build_pnl,
    build_scenarios,
    calculate_kpis,
    clean_balance_sheet_df,
    clean_financial_df,
    combined_actual_budget_forecast,
    derive_simple_balance_sheet,
    latest_actual_month,
    normalize_section,
    pnl_pivot_for_display,
    variance_analysis,
)
from src.storage import list_runs, save_run


APP_TITLE = "FP&A Dashboard: Budget, Forecast, P&L, Variance, and Balance Sheet"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SAMPLE_ACTUALS = DATA_DIR / "sample_actuals.csv"
SAMPLE_BUDGET = DATA_DIR / "sample_budget.csv"
SAMPLE_BALANCE = DATA_DIR / "sample_balance_sheet.csv"
TEMPLATE = DATA_DIR / "upload_template.xlsx"


st.set_page_config(
    page_title="FP&A Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------
# Styling helpers
# -----------------------------

def section_header(title: str, caption: str | None = None) -> None:
    st.subheader(title)
    if caption:
        st.caption(caption)


def display_metric(label: str, value: float, delta: float | None = None, is_percent: bool = False) -> None:
    formatted_value = percent(value) if is_percent else dollars(value)
    formatted_delta = None
    if delta is not None:
        formatted_delta = percent(delta) if is_percent else dollars(delta)
    st.metric(label, formatted_value, formatted_delta)


def display_ratio_metric(label: str, value: float) -> None:
    """Display non-currency ratios such as current ratio or debt-to-equity."""
    st.metric(label, f"{value:.2f}x")


def format_money_df(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """Return a basic currency-formatted Styler for display tables."""
    if df.empty:
        return df.style
    money_cols = [c for c in df.columns if c not in {"P&L Line", "section", "account", "favorability", "commentary"}]
    return df.style.format({c: "${:,.0f}" for c in money_cols if pd.api.types.is_numeric_dtype(df[c])})

def display_actual_budget_forecast_note(actual_month: pd.Timestamp | None, fiscal_year: int) -> None:
    """
    Display a short explanation of how actuals, budget, and forecast periods relate.

    Actuals usually exist only through the latest closed month.
    Budget usually covers the full fiscal year.
    Forecast begins after the latest actual month.
    """
    if actual_month is None:
        st.caption("No actual months are currently loaded.")
        return

    latest_actual = pd.to_datetime(actual_month)
    next_forecast_month = latest_actual + pd.offsets.MonthBegin(1)

    st.caption(
        f"Actuals are shown through {latest_actual.strftime('%b %Y')}. "
        f"Budget covers fiscal year {int(fiscal_year)}. "
        f"Base forecast begins in {next_forecast_month.strftime('%b %Y')}."
    )


def display_variance_note(actual_month: pd.Timestamp | None) -> None:
    """
    Display a short explanation of the budget vs actual variance logic.

    This helps users understand that variance analysis should compare actuals
    only against matching budget months, not against the full-year budget.
    """
    if actual_month is None:
        st.caption("Variance analysis requires actuals and budget data for matching months.")
        return

    latest_actual = pd.to_datetime(actual_month)

    st.caption(
        f"Variance analysis compares actuals through {latest_actual.strftime('%b %Y')} "
        "against the same budget months only. Revenue above budget is favorable. "
        "Expenses below budget are favorable."
    )


def display_balance_sheet_note(balance_kpis: dict) -> None:
    """
    Display a short explanation of the balance sheet check.

    The balance sheet is correct when Assets = Liabilities + Equity.
    The Balance Check value should be close to zero.
    """
    balance_check = balance_kpis["Balance Check"]

    st.caption(
        "Balance check uses Assets - Liabilities - Equity. "
        "A value near zero means the balance sheet balances. "
        f"Current balance check: {balance_check:,.0f} dollars."
    )

# -----------------------------
# Upload role validation helpers
# -----------------------------

BALANCE_SHEET_SECTIONS = {
    "current asset",
    "current assets",
    "noncurrent asset",
    "noncurrent assets",
    "non current asset",
    "non current assets",
    "current liability",
    "current liabilities",
    "noncurrent liability",
    "noncurrent liabilities",
    "non current liability",
    "non current liabilities",
    "equity",
}

FINANCIAL_ROLE_WORDS = {
    "actual",
    "actuals",
    "budget",
    "forecast",
    "p&l",
    "pnl",
}


def normalize_text(value: object) -> str:
    """
    Normalize text for forgiving validation comparisons.

    This keeps validation stable across labels like:
    - Noncurrent Asset
    - Non-current Asset
    - noncurrent_asset
    """
    return " ".join(
        str(value)
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
        .split()
    )


def find_column(df: pd.DataFrame, possible_names: set[str]) -> str | None:
    """
    Find a column in a dataframe using normalized names.

    This allows the app to recognize common variations like:
    - line item
    - line_item
    - account
    - account_name
    """
    normalized_lookup = {normalize_text(col): col for col in df.columns}

    for name in possible_names:
        normalized_name = normalize_text(name)
        if normalized_name in normalized_lookup:
            return normalized_lookup[normalized_name]

    return None


def get_normalized_section_values(df: pd.DataFrame) -> set[str]:
    """Return normalized values from the section/category/type column."""
    section_col = find_column(df, {"section", "category", "statement_section", "type"})

    if section_col is None:
        return set()

    return {
        normalize_text(value)
        for value in df[section_col].dropna().unique()
        if str(value).strip()
    }


def get_normalized_scenario_values(df: pd.DataFrame) -> set[str]:
    """Return normalized values from the optional scenario column."""
    scenario_col = find_column(df, {"scenario"})

    if scenario_col is None:
        return set()

    return {
        normalize_text(value)
        for value in df[scenario_col].dropna().unique()
        if str(value).strip()
    }


def get_pnl_section_values(df: pd.DataFrame) -> set[str]:
    """
    Return section values that match valid P&L sections.

    The finance engine already knows aliases like sales, opex, and income tax.
    This function reuses that logic so validation matches the model.
    """
    raw_sections = get_normalized_section_values(df)
    normalized_valid_sections = {normalize_text(section) for section in VALID_SECTIONS}

    matched_sections = set()

    for raw_section in raw_sections:
        cleaned = normalize_section(raw_section)
        cleaned_normalized = normalize_text(cleaned)

        if cleaned_normalized in normalized_valid_sections:
            matched_sections.add(cleaned_normalized)

    return matched_sections


def validate_financial_upload(raw_df: pd.DataFrame, slot_name: str, uploaded_file: object | None) -> None:
    """
    Validate actuals and budget uploads before the model cleans them.

    Actuals and budget files intentionally share the same structure, so this
    function checks role clues such as file name and scenario column.
    """
    if raw_df is None or raw_df.empty:
        return

    expected_role = "actual" if slot_name == "Actuals" else "budget"
    opposite_role = "budget" if expected_role == "actual" else "actual"

    file_name = normalize_text(getattr(uploaded_file, "name", "")) if uploaded_file is not None else ""
    scenario_values = get_normalized_scenario_values(raw_df)
    raw_sections = get_normalized_section_values(raw_df)
    pnl_sections = get_pnl_section_values(raw_df)
    balance_sections = raw_sections.intersection(BALANCE_SHEET_SECTIONS)

    # Catch obvious file-name mistakes such as sample_budget.csv in the Actuals slot.
    if uploaded_file is not None and opposite_role in file_name:
        raise ValueError(
            f"The {slot_name} upload appears to be a {opposite_role} file based on its file name. "
            f"Please upload it to the {opposite_role.title()} slot instead."
        )

    if uploaded_file is not None and "balance" in file_name:
        raise ValueError(
            f"The {slot_name} upload appears to be a balance sheet file based on its file name. "
            "Please upload it to the Balance Sheet slot instead."
        )

    # Catch sample/custom files that include a scenario column.
    if scenario_values and expected_role not in scenario_values:
        raise ValueError(
            f"The {slot_name} upload has scenario value(s): {', '.join(sorted(scenario_values))}. "
            f"This slot expects {expected_role.title()} data."
        )

    # Prevent a balance sheet from being used as actuals or budget.
    if balance_sections and not pnl_sections:
        raise ValueError(
            f"The {slot_name} upload looks like a balance sheet because it contains balance sheet sections. "
            "Please upload it to the Balance Sheet slot."
        )

    # Require at least one valid P&L section for actuals/budget.
    if not pnl_sections:
        raise ValueError(
            f"The {slot_name} upload does not contain recognizable P&L sections. "
            "Expected sections like Revenue, COGS, Operating Expense, Other Income, Other Expense, or Tax."
        )


def validate_balance_sheet_upload(raw_df: pd.DataFrame, uploaded_file: object | None) -> None:
    """
    Validate balance sheet uploads before the model cleans them.

    This prevents actuals or budget files from being treated as a balance sheet.
    """
    if raw_df is None or raw_df.empty:
        return

    file_name = normalize_text(getattr(uploaded_file, "name", "")) if uploaded_file is not None else ""
    raw_sections = get_normalized_section_values(raw_df)
    pnl_sections = get_pnl_section_values(raw_df)
    balance_sections = raw_sections.intersection(BALANCE_SHEET_SECTIONS)
    scenario_values = get_normalized_scenario_values(raw_df)

    # Catch obvious file-name mistakes.
    if uploaded_file is not None:
        for role_word in FINANCIAL_ROLE_WORDS:
            if role_word in file_name and "balance" not in file_name:
                raise ValueError(
                    "The Balance Sheet upload appears to be an actuals, budget, forecast, or P&L file "
                    "based on its file name. Please upload a real balance sheet file."
                )

    # Catch actuals/budget files that have P&L sections instead of balance sheet sections.
    if pnl_sections and not balance_sections:
        raise ValueError(
            "The Balance Sheet upload looks like an actuals/budget/P&L file because it contains "
            "P&L sections such as Revenue, COGS, Operating Expense, Other Expense, or Tax. "
            "Please upload a balance sheet file with sections such as Current Asset, "
            "Noncurrent Asset, Current Liability, Noncurrent Liability, or Equity."
        )

    # Catch files with no recognizable balance sheet sections.
    if not balance_sections:
        raise ValueError(
            "The Balance Sheet upload does not contain recognizable balance sheet sections. "
            "Expected Current Asset, Noncurrent Asset, Current Liability, Noncurrent Liability, or Equity."
        )

    # A balance sheet usually should not have Actual/Budget/Forecast scenario values.
    if scenario_values:
        raise ValueError(
            "The Balance Sheet upload contains a scenario column, which usually means it is an actuals, "
            "budget, or forecast file. Please upload a balance sheet file instead."
        )

# -----------------------------
# Sidebar: uploads and assumptions
# -----------------------------

st.title(APP_TITLE)
st.write(
    "A  corporate finance project that connects actuals, budgets, rolling forecasts, "
    "P&L reporting, balance sheet reporting, variance analysis, dashboard visuals, SQLite run history, "
    "and Excel report generation."
)

with st.sidebar:
    st.header("1. Upload Finance Data")
    st.caption("Use the included sample files first, then replace them with your own CSV/XLSX files.")

    with open(TEMPLATE, "rb") as f:
        st.download_button(
            "Download Upload Template",
            data=f,
            file_name="fpa_upload_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    actuals_file = st.file_uploader("Actuals CSV/XLSX", type=["csv", "xlsx", "xlsm", "xls"], key="actuals")
    budget_file = st.file_uploader("Budget CSV/XLSX", type=["csv", "xlsx", "xlsm", "xls"], key="budget")
    balance_file = st.file_uploader("Balance Sheet CSV/XLSX", type=["csv", "xlsx", "xlsm", "xls"], key="balance")

    st.divider()
    st.header("2. Forecast Assumptions")
    fiscal_year = st.number_input("Fiscal year", min_value=2020, max_value=2035, value=2026, step=1)
    monthly_revenue_growth = st.slider("Base monthly revenue growth", -0.10, 0.20, 0.025, 0.005)
    cogs_percent = st.slider("COGS as % of revenue", 0.05, 0.80, 0.28, 0.01)
    monthly_opex_growth = st.slider("Monthly OpEx growth", -0.05, 0.10, 0.010, 0.005)
    monthly_other_expense_growth = st.slider("Monthly other expense growth", -0.05, 0.10, 0.000, 0.005)
    effective_tax_rate = st.slider("Effective tax rate", 0.00, 0.45, 0.21, 0.01)
    monthly_new_headcount_cost = st.number_input("Monthly incremental headcount cost", min_value=0.0, value=0.0, step=2500.0)

    st.divider()
    st.header("3. Run History")
    show_history = st.checkbox("Show saved SQLite runs", value=False)


# -----------------------------
# Load, clean, and validate inputs
# -----------------------------

try:
    raw_actuals = read_table(actuals_file, SAMPLE_ACTUALS)
    raw_budget = read_table(budget_file, SAMPLE_BUDGET)
    raw_balance = read_table(balance_file, SAMPLE_BALANCE if balance_file is not None else None)

    validate_financial_upload(raw_actuals, "Actuals", actuals_file)
    validate_financial_upload(raw_budget, "Budget", budget_file)

    if not raw_balance.empty:
        validate_balance_sheet_upload(raw_balance, balance_file)

    actuals = clean_financial_df(raw_actuals, "Actual")
    budget = clean_financial_df(raw_budget, "Budget")

    # Give users a simple in-app way to tweak budget data without opening Excel.
    with st.expander("Optional: edit budget inputs inside the app", expanded=False):
        st.caption(
            "This editor is useful for demonstrating a budget-planning workflow. "
            "You can edit amounts, departments, sections, accounts, or months before the model runs."
        )
        editable_budget = budget.copy()
        editable_budget["month"] = editable_budget["month"].dt.strftime("%Y-%m-%d")
        edited_budget = st.data_editor(
            editable_budget,
            num_rows="dynamic",
            use_container_width=True,
            key="budget_editor",
        )
        budget = clean_financial_df(edited_budget, "Budget")

    if raw_balance.empty:
        balance_sheet = derive_simple_balance_sheet(actuals)
        balance_source = "Derived demo balance sheet because no balance sheet file was uploaded."
    else:
        balance_sheet = clean_balance_sheet_df(raw_balance)
        balance_source = "Uploaded balance sheet."

except Exception as exc:
    st.error(f"Data loading error: {exc}")
    st.stop()


# -----------------------------
# Forecast generation
# -----------------------------

base_assumptions = ForecastAssumptions(
    monthly_revenue_growth=monthly_revenue_growth,
    cogs_percent_of_revenue=cogs_percent,
    monthly_opex_growth=monthly_opex_growth,
    monthly_other_expense_growth=monthly_other_expense_growth,
    effective_tax_rate=effective_tax_rate,
    monthly_new_headcount_cost=monthly_new_headcount_cost,
)

# Scenario logic: upside and downside are intentionally derived from the base case
# to show how FP&A models sensitivity around management assumptions.
scenario_assumptions = ScenarioAssumptions(
    base=base_assumptions,
    upside=ForecastAssumptions(
        monthly_revenue_growth=monthly_revenue_growth + 0.015,
        cogs_percent_of_revenue=max(cogs_percent - 0.02, 0.01),
        monthly_opex_growth=max(monthly_opex_growth - 0.005, -0.05),
        monthly_other_expense_growth=monthly_other_expense_growth,
        effective_tax_rate=effective_tax_rate,
        monthly_new_headcount_cost=monthly_new_headcount_cost,
    ),
    downside=ForecastAssumptions(
        monthly_revenue_growth=monthly_revenue_growth - 0.020,
        cogs_percent_of_revenue=min(cogs_percent + 0.03, 0.95),
        monthly_opex_growth=monthly_opex_growth + 0.010,
        monthly_other_expense_growth=monthly_other_expense_growth,
        effective_tax_rate=effective_tax_rate,
        monthly_new_headcount_cost=monthly_new_headcount_cost,
    ),
)

forecast = build_scenarios(actuals, budget, int(fiscal_year), scenario_assumptions)
combined = combined_actual_budget_forecast(actuals, budget, forecast)
pnl = build_pnl(combined)
variance = variance_analysis(actuals, budget)
balance_summary, balance_kpis = balance_sheet_summary(balance_sheet)

actual_month = latest_actual_month(actuals)
actual_months = sorted(actuals["month"].unique()) if not actuals.empty else []
actual_kpis = calculate_kpis(pnl, "Actual")
budget_kpis_ytd = calculate_kpis(pnl, "Budget", months=actual_months)
base_forecast_kpis = calculate_kpis(pnl, "Base Forecast")


# -----------------------------
# Dashboard tabs
# -----------------------------

tabs = st.tabs(
    [
        "Executive Summary",
        "P&L Report",
        "Variance Analysis",
        "Forecast & Scenarios",
        "Balance Sheet",
        "Data Quality",
        "Excel Export",
    ]
)


with tabs[0]:
    section_header(
        "Executive Summary",
        "High-level FP&A view of actual YTD performance, budget comparison, and forecasted year-end outcome.",
    )

    if actual_month is not None:
        st.info(f"Latest actual month loaded: **{actual_month.strftime('%B %Y')}**")

    display_actual_budget_forecast_note(actual_month, fiscal_year)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        display_metric("YTD Revenue", actual_kpis["Revenue"], actual_kpis["Revenue"] - budget_kpis_ytd["Revenue"])
    with col2:
        display_metric("YTD Gross Margin", actual_kpis["Gross Margin"], actual_kpis["Gross Margin"] - budget_kpis_ytd["Gross Margin"], True)
    with col3:
        display_metric("YTD Operating Income", actual_kpis["Operating Income"], actual_kpis["Operating Income"] - budget_kpis_ytd["Operating Income"])
    with col4:
        display_metric("YTD Net Income", actual_kpis["Net Income"], actual_kpis["Net Income"] - budget_kpis_ytd["Net Income"])

    col5, col6, col7, col8 = st.columns(4)
    with col5:
        display_metric("Forecast Revenue", base_forecast_kpis["Revenue"])
    with col6:
        display_metric("Forecast Net Income", base_forecast_kpis["Net Income"])
    with col7:
        cash_value = balance_sheet.loc[balance_sheet["line_item"].str.lower().str.contains("cash", na=False), "amount"].sum()
        display_metric("Cash", cash_value)
    with col8:
        display_metric("Balance Check", balance_kpis["Balance Check"])

    trend = pnl[pnl["pnl_line"].astype(str).isin(["Revenue", "Gross Profit", "Operating Income", "Net Income"])]
    trend = trend[trend["scenario"].isin(["Actual", "Budget", "Base Forecast"])]
    fig = px.line(
        trend,
        x="month",
        y="amount",
        color="pnl_line",
        line_dash="scenario",
        markers=True,
        title="Revenue, Margin, and Profitability Trend",
        labels={"amount": "Amount", "month": "Month", "pnl_line": "P&L Line", "scenario": "Scenario"},
    )
    st.plotly_chart(fig, use_container_width=True)

    top_comments = variance.head(5)[["section", "account", "variance", "favorability", "commentary"]]
    st.write("#### Top Variance Commentary")
    st.dataframe(top_comments, use_container_width=True, hide_index=True)


with tabs[1]:
    section_header(
        "P&L Report",
        "Management-style Profit and Loss report. Revenue and income lines are shown alongside cost and expense lines.",
    )

    scenario_choice = st.selectbox(
        "Select scenario",
        ["Actual", "Budget", "Base Forecast", "Upside Forecast", "Downside Forecast"],
        index=0,
    )
    display_pnl = pnl_pivot_for_display(pnl, scenario_choice)
    st.dataframe(format_money_df(display_pnl), use_container_width=True, hide_index=True)

    monthly_net_income = pnl[(pnl["pnl_line"].astype(str) == "Net Income") & (pnl["scenario"].isin(["Actual", "Budget", "Base Forecast"]))]
    fig = px.bar(
        monthly_net_income,
        x="month",
        y="amount",
        color="scenario",
        barmode="group",
        title="Net Income by Month: Actual vs Budget vs Base Forecast",
        labels={"amount": "Net Income", "month": "Month"},
    )
    st.plotly_chart(fig, use_container_width=True)

    display_actual_budget_forecast_note(actual_month, fiscal_year)


with tabs[2]:
    section_header(
        "Budget vs Actual Variance Analysis",
        "Compares actual results against the budget for months where actuals exist. This mirrors a common FP&A monthly close workflow.",
    )

    display_variance_note(actual_month)
    
    if variance.empty:
        st.warning("Variance analysis requires both actuals and budget data.")
    else:
        st.dataframe(
            variance.style.format(
                {
                    "actual": "${:,.0f}",
                    "budget": "${:,.0f}",
                    "variance": "${:,.0f}",
                    "variance_pct": "{:.1%}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        variance_chart = variance.head(12).copy()
        variance_chart["label"] = variance_chart["section"] + " - " + variance_chart["account"]
        fig = px.bar(
            variance_chart.sort_values("variance"),
            x="variance",
            y="label",
            color="favorability",
            orientation="h",
            title="Largest Budget vs Actual Variances",
            labels={"variance": "Actual - Budget", "label": "Account"},
        )
        st.plotly_chart(fig, use_container_width=True)

        st.caption(
            "Bars show Actual - Budget by account. Positive revenue variances are favorable, "
            "while positive expense variances are unfavorable."
        )


with tabs[3]:
    section_header(
        "Forecast & Scenarios",
        "Base, upside, and downside views based on driver assumptions. This demonstrates how finance teams model uncertainty.",
    )

    display_actual_budget_forecast_note(actual_month, fiscal_year)
    

    scenario_lines = pnl[(pnl["pnl_line"].astype(str).isin(["Revenue", "Net Income"])) & (pnl["scenario"].str.contains("Forecast"))]
    fig = px.line(
        scenario_lines,
        x="month",
        y="amount",
        color="scenario",
        line_dash="pnl_line",
        markers=True,
        title="Forecast Scenarios: Revenue and Net Income",
        labels={"amount": "Amount", "month": "Month"},
    )
    st.plotly_chart(fig, use_container_width=True)

    scenario_summary_rows = []
    for s in ["Base Forecast", "Upside Forecast", "Downside Forecast"]:
        k = calculate_kpis(pnl, s)
        scenario_summary_rows.append(
            {
                "Scenario": s,
                "Forecast Revenue": k["Revenue"],
                "Gross Margin": k["Gross Margin"],
                "Operating Income": k["Operating Income"],
                "Net Income": k["Net Income"],
                "Net Margin": k["Net Margin"],
            }
        )
    scenario_summary = pd.DataFrame(scenario_summary_rows)
    st.dataframe(
        scenario_summary.style.format(
            {
                "Forecast Revenue": "${:,.0f}",
                "Gross Margin": "{:.1%}",
                "Operating Income": "${:,.0f}",
                "Net Income": "${:,.0f}",
                "Net Margin": "{:.1%}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.write("#### Forecast Detail")
    st.dataframe(forecast, use_container_width=True, hide_index=True)


with tabs[4]:
    section_header(
        "Balance Sheet Snapshot",
        "Shows what the company owns, owes, and the remaining equity value at a point in time.",
    )
    st.caption(balance_source)
    display_balance_sheet_note(balance_kpis)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        display_metric("Total Assets", balance_kpis["Total Assets"])
    with col2:
        display_metric("Total Liabilities", balance_kpis["Total Liabilities"])
    with col3:
        display_metric("Total Equity", balance_kpis["Total Equity"])
    with col4:
        display_ratio_metric("Current Ratio", balance_kpis["Current Ratio"])

    col5, col6 = st.columns(2)
    with col5:
        st.write("#### Balance Sheet Detail")
        st.dataframe(balance_sheet, use_container_width=True, hide_index=True)
    with col6:
        st.write("#### Section Summary")
        st.dataframe(balance_summary, use_container_width=True, hide_index=True)
        fig = px.pie(balance_summary, values="amount", names="section", title="Balance Sheet Composition")
        st.plotly_chart(fig, use_container_width=True)

        st.caption(
            "The pie chart shows how assets, liabilities, and equity are distributed across balance sheet sections."
        )

    if abs(balance_kpis["Balance Check"]) > 1:
        st.warning(
            "The balance sheet does not balance. Check whether Assets = Liabilities + Equity. "
            f"Current difference: {dollars(balance_kpis['Balance Check'])}."
        )
    else:
        st.success("Balance sheet balances: Assets = Liabilities + Equity.")


with tabs[5]:
    section_header(
        "Data Quality and Input Preview",
        "Validates whether the uploaded files have the columns and values required for FP&A reporting.",
    )

    st.success("Input files passed schema and role validation.")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.write("#### Actuals")
        st.dataframe(actuals.head(50), use_container_width=True, hide_index=True)
        st.caption(f"Rows: {len(actuals):,}")
    with col2:
        st.write("#### Budget")
        st.dataframe(budget.head(50), use_container_width=True, hide_index=True)
        st.caption(f"Rows: {len(budget):,}")
    with col3:
        st.write("#### Balance Sheet")
        st.dataframe(balance_sheet.head(50), use_container_width=True, hide_index=True)
        st.caption(f"Rows: {len(balance_sheet):,}")

    st.write("#### Required Input Schema")
    st.markdown(
        """
        **Actuals/Budget files** require these columns:
        - `month`: date or month such as `2026-01-01`
        - `section`: `Revenue`, `COGS`, `Operating Expense`, `Other Income`, `Other Expense`, or `Tax`
        - `account`: account or line-item name
        - `amount`: positive dollar amount
        - `department`: optional department or cost center
        - `scenario`: optional, but if included, actuals files should say `Actual` and budget files should say `Budget`

        **Balance sheet files** require:
        - `as_of_date`: optional date
        - `section`: `Current Asset`, `Noncurrent Asset`, `Current Liability`, `Noncurrent Liability`, or `Equity`
        - `line_item`: account name
        - `amount`: dollar balance
        """
    )

    if show_history:
        st.write("#### Saved SQLite Runs")
        st.dataframe(list_runs(), use_container_width=True, hide_index=True)


with tabs[6]:
    section_header(
        "Excel Export and Save Run",
        "Exports the dashboard into an Excel reporting package with executive summary, P&L reports, variance analysis, forecast detail, and balance sheet tabs.",
    )

    report_bytes = create_excel_report(
        actuals=actuals,
        budget=budget,
        forecast=forecast,
        pnl=pnl,
        variance=variance,
        balance_sheet=balance_sheet,
        balance_summary=balance_summary,
        kpis=actual_kpis,
    )

    st.download_button(
        "Download Excel FP&A Report",
        data=report_bytes,
        file_name="fpa_management_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.write("#### Save Analysis Run Locally")
    run_name = st.text_input("Run name", value="Monthly FP&A Review")
    if st.button("Save run to SQLite"):
        run_id = save_run(
            run_name=run_name,
            assumptions={
                "fiscal_year": int(fiscal_year),
                "monthly_revenue_growth": monthly_revenue_growth,
                "cogs_percent_of_revenue": cogs_percent,
                "monthly_opex_growth": monthly_opex_growth,
                "monthly_other_expense_growth": monthly_other_expense_growth,
                "effective_tax_rate": effective_tax_rate,
                "monthly_new_headcount_cost": monthly_new_headcount_cost,
            },
            tables={
                "actuals": actuals,
                "budget": budget,
                "forecast": forecast,
                "variance": variance,
                "balance_sheet": balance_sheet,
            },
        )
        st.success(f"Saved run #{run_id} to local SQLite database fpa_runs.db.")


st.caption(
    "Built for FP&A/corporate finance portfolio use."
)
