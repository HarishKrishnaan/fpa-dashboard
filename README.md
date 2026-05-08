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
```
---

# Local Setup Instructions

## 1. Install Python

Make sure Python 3 is installed.

Check with:

```bash
python --version
```

On Windows, this may be:

```bash
py --version
```

If Python is not installed, install it first. On Windows, make sure to select:

```text
Add python.exe to PATH
```

during installation.

---

## 2. Open the Project Folder

Open the project folder in VSCode.

The folder should contain:

```text
app.py
requirements.txt
data/
src/
```

Open a terminal in VSCode:

```text
Terminal > New Terminal
```

---

## 3. Create a Virtual Environment

### Windows PowerShell

```powershell
py -3 -m venv .venv
```

Alternative:

```powershell
python -m venv .venv
```

### Mac/Linux

```bash
python3 -m venv .venv
```

---

## 4. Activate the Virtual Environment

### Windows PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then activate again:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Mac/Linux

```bash
source .venv/bin/activate
```

After activation, the terminal should show:

```text
(.venv)
```

---

## 5. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 6. Run the App

```bash
streamlit run app.py
```

If that does not work, run:

```bash
python -m streamlit run app.py
```

The app should open in your browser.

The local URL is usually:

```text
http://localhost:8501
```

---

## Windows Shortcut Without Activation

If the virtual environment activation does not work, run the app directly with:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

---

# How to Use the App

## 1. Upload Sample Files

Sample files are included in the `data/` folder.

Use these files first:

| Upload Slot | File |
|---|---|
| Actuals CSV/XLSX | `data/sample_actuals.csv` |
| Budget CSV/XLSX | `data/sample_budget.csv` |
| Balance Sheet CSV/XLSX | `data/sample_balance_sheet.csv` |

The app also has built-in demo data, so it can run even if no files are uploaded.

---

## 2. Executive Summary

The Executive Summary tab shows:

- YTD revenue
- YTD gross margin
- YTD operating income
- YTD net income
- Forecast revenue
- Forecast net income
- Cash
- Balance check
- Main financial trends
- Top variance commentary

---

## 3. P&L Report

The P&L Report tab shows a management-style profit and loss statement.

It includes:

- Revenue
- COGS
- Gross profit
- Operating expenses
- Operating income
- Other income
- Other expense
- Pre-tax income
- Tax
- Net income

Actuals are shown through the latest actual month. Budget covers the full fiscal year. Forecast begins after the latest actual month.

---

## 4. Variance Analysis

The Variance Analysis tab compares actuals against budget for the same months.

The app uses:

```text
Variance = Actual - Budget
```

For revenue, actuals above budget are favorable.

For expenses, actuals below budget are favorable.

The app also generates written commentary for the largest variances.

---

## 5. Forecast & Scenarios

The Forecast & Scenarios tab shows:

- Base forecast
- Upside forecast
- Downside forecast
- Forecast revenue
- Gross margin
- Operating income
- Net income
- Net margin

Forecast assumptions can be adjusted from the sidebar.

---

## 6. Balance Sheet

The Balance Sheet tab shows:

- Total assets
- Total liabilities
- Total equity
- Current ratio
- Balance sheet detail
- Section summary
- Balance sheet composition chart

The balance check uses:

```text
Assets - Liabilities - Equity
```

A value near zero means the balance sheet balances.

---

## 7. Data Quality

The Data Quality tab previews the uploaded files and shows the required file structure.

The app validates whether files are uploaded into the correct slots.

For example:

- Actuals files should go in the Actuals upload slot
- Budget files should go in the Budget upload slot
- Balance sheet files should go in the Balance Sheet upload slot

---

## 8. Excel Export and Save Run

The Excel Export tab allows users to download an Excel report.

Click:

```text
Download Excel FP&A Report
```

This exports the dashboard results into an Excel workbook.

The same tab also allows users to save a run locally with SQLite.

Click:

```text
Save run to SQLite
```

This creates or updates a local database file:

```text
fpa_runs.db
```

---

# Upload File Requirements

## Actuals and Budget Files

Required columns:

| Column | Description |
|---|---|
| `month` | Month or date |
| `section` | P&L section |
| `account` | Account or line item |
| `amount` | Dollar amount |
| `department` | Optional department |
| `scenario` | Optional, but useful for identifying Actual or Budget files |

Valid P&L sections:

```text
Revenue
COGS
Operating Expense
Other Income
Other Expense
Tax
```

---

## Balance Sheet Files

Required columns:

| Column | Description |
|---|---|
| `as_of_date` | Optional balance sheet date |
| `section` | Balance sheet section |
| `line_item` | Account name |
| `amount` | Dollar balance |

Valid balance sheet sections:

```text
Current Asset
Noncurrent Asset
Current Liability
Noncurrent Liability
Equity
```

---

# Troubleshooting

## Python command not found

Try:

```powershell
py --version
```

If that works, use `py` instead of `python` for setup commands.

Example:

```powershell
py -3 -m venv .venv
```

---

## Streamlit command not found

Run:

```bash
python -m streamlit run app.py
```

Or on Windows:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

---

## Streamlit asks for an email

Streamlit may ask for an optional email during first launch.

You can leave it blank and press Enter.

---