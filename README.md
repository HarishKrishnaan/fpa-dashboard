# FP&A Dashboard: Budget, Forecast, P&L, Variance, and Balance Sheet

This project is a corporate finance and FP&A dashboard built with Python and Streamlit. It allows users to upload financial actuals, budget files, and balance sheet files, then generate management-style financial reports, variance analysis, rolling forecasts, scenario views, charts, and Excel exports.

The goal of this project is to demonstrate how corporate finance concepts such as budgeting, forecasting, P&L reporting, balance sheets, and variance analysis can be connected through a working software application.

---

## Features

- Upload actual financial results from CSV or Excel files
- Upload budget data from CSV or Excel files
- Upload balance sheet data from CSV or Excel files
- Validate uploaded files to prevent actuals, budget, and balance sheet files from being placed in the wrong upload slots
- Generate a management-style P&L report
- Compare actuals against budget
- Calculate favorable and unfavorable variances
- Generate automated variance commentary
- Build base, upside, and downside forecast scenarios
- Display revenue, gross profit, operating income, and net income trends
- Display balance sheet metrics including assets, liabilities, equity, current ratio, and balance check
- Export an Excel FP&A management report
- Save analysis runs locally using SQLite

---

## Finance Concepts Demonstrated

This project demonstrates several core FP&A and corporate finance concepts:

| Concept | How It Appears in the Project |
|---|---|
| Budgeting | Users can upload or edit budget data for the fiscal year |
| Actuals | Users can upload monthly actual financial performance |
| Forecasting | The app creates base, upside, and downside forecast scenarios |
| P&L Statement | The app generates revenue, COGS, gross profit, operating expense, operating income, tax, and net income |
| Variance Analysis | The app compares actuals against budget and labels results as favorable or unfavorable |
| Balance Sheet | The app reports assets, liabilities, equity, current ratio, and balance check |
| Excel Reporting | The app exports a finance report to Excel for management-style review |

---

## Tech Stack

- Python
- Streamlit
- Pandas
- Plotly
- SQLite
- openpyxl
- Excel / CSV file processing

---

## Project Structure

```text
fpa_dashboard_project/
│
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
│
├── data/
│   ├── sample_actuals.csv
│   ├── sample_budget.csv
│   ├── sample_balance_sheet.csv
│   └── upload_template.xlsx
│
└── src/
    ├── data_loader.py
    ├── excel_exporter.py
    ├── finance_engine.py
    └── storage.py