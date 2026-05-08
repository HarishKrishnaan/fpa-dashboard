"""Basic smoke tests for the finance engine."""

from pathlib import Path

import pandas as pd

from src.finance_engine import (
    ForecastAssumptions,
    build_pnl,
    clean_financial_df,
    generate_forecast,
    variance_analysis,
)


def test_pnl_has_net_income():
    data = pd.DataFrame(
        [
            {"month": "2026-01-01", "section": "Revenue", "account": "Sales", "amount": 100},
            {"month": "2026-01-01", "section": "COGS", "account": "COGS", "amount": 40},
            {"month": "2026-01-01", "section": "Operating Expense", "account": "Payroll", "amount": 20},
            {"month": "2026-01-01", "section": "Tax", "account": "Tax", "amount": 8},
        ]
    )
    cleaned = clean_financial_df(data, "Actual")
    pnl = build_pnl(cleaned)
    net_income = pnl.loc[pnl["pnl_line"].astype(str).eq("Net Income"), "amount"].sum()
    assert net_income == 32


def test_forecast_generates_future_months():
    actuals = pd.DataFrame(
        [
            {"month": "2026-01-01", "section": "Revenue", "account": "Sales", "amount": 100},
            {"month": "2026-01-01", "section": "COGS", "account": "COGS", "amount": 30},
            {"month": "2026-01-01", "section": "Operating Expense", "account": "Payroll", "amount": 20},
        ]
    )
    actuals = clean_financial_df(actuals, "Actual")
    forecast = generate_forecast(actuals, pd.DataFrame(), ForecastAssumptions(), 2026)
    assert not forecast.empty
    assert forecast["month"].min() == pd.Timestamp("2026-02-01")


def test_variance_analysis_identifies_difference():
    actuals = clean_financial_df(
        pd.DataFrame([{"month": "2026-01-01", "section": "Revenue", "account": "Sales", "amount": 110}]),
        "Actual",
    )
    budget = clean_financial_df(
        pd.DataFrame([{"month": "2026-01-01", "section": "Revenue", "account": "Sales", "amount": 100}]),
        "Budget",
    )
    variance = variance_analysis(actuals, budget)
    assert variance.iloc[0]["variance"] == 10
    assert variance.iloc[0]["favorability"] == "Favorable"
