"""
Streamlit Expense Manager - single-file app
Requirements: streamlit, gspread, google-auth, pandas

How this file expects secrets (set in Streamlit Cloud > Secrets):
- GOOGLE_SHEET_KEY: the Google Sheets spreadsheet ID
- GCP_SERVICE_ACCOUNT: the full service account JSON as a single-line string (JSON text). Example value: '{"type": "service_account", "project_id": ... }'

The app will ensure the following worksheets exist and create them if missing:
- Budgets  (header: Week1,Week2,Week3,Week4,Week5,Misc_Budget,Month,Updated)
- Week1, Week2, Week3, Week4, Week5, Misc  (header: Timestamp,Description,Amount)

Usage: paste this file into your repo as streamlit_app.py and deploy to Streamlit Cloud.
"""

import streamlit as st
import gspread
import json
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

# ----------------- CONFIG -----------------
WEEK_SHEETS = [f"Week{i}" for i in range(1,6)]
MISC_SHEET = "Misc"
BUDGET_SHEET = "Budgets"
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ----------------- GSheets HELPERS -----------------
@st.cache_resource
def get_gspread_client():
    # Expect secrets: GCP_SERVICE_ACCOUNT (JSON string), GOOGLE_SHEET_KEY
    if "GCP_SERVICE_ACCOUNT" not in st.secrets:
        st.error("Missing secret: GCP_SERVICE_ACCOUNT. See setup instructions in repo README.")
        st.stop()
    if "GOOGLE_SHEET_KEY" not in st.secrets:
        st.error("Missing secret: GOOGLE_SHEET_KEY. Add the spreadsheet ID in Streamlit secrets.")
        st.stop()

    creds_info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPE)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(st.secrets["GOOGLE_SHEET_KEY"])  # may raise error if key wrong
    return sh


def ensure_sheets(sh):
    # create necessary worksheets if missing
    existing = {ws.title for ws in sh.worksheets()}
    # Budgets
    if BUDGET_SHEET not in existing:
        sh.add_worksheet(title=BUDGET_SHEET, rows=10, cols=20)
        ws = sh.worksheet(BUDGET_SHEET)
        headers = ["Week1","Week2","Week3","Week4","Week5","Misc_Budget","Month","Updated"]
        ws.append_row(headers)
        # append an initial zero row
        ws.append_row([0,0,0,0,0,0, datetime.now().strftime("%Y-%m") , datetime.now().isoformat()])
    # weeks + misc
    for name in WEEK_SHEETS + [MISC_SHEET]:
        if name not in existing:
            sh.add_worksheet(title=name, rows=1000, cols=10)
            ws = sh.worksheet(name)
            ws.append_row(["Timestamp","Description","Amount"])


def read_budgets(sh):
    ws = sh.worksheet(BUDGET_SHEET)
    rows = ws.get_all_values()
    if len(rows) < 2:
        return {f"Week{i+1}":0 for i in range(5)}, 0
    headers = rows[0]
    values = rows[1]
    d = {}
    for h,v in zip(headers, values):
        if h.startswith("Week") or h=="Misc_Budget":
            try:
                d[h] = float(v)
            except:
                d[h] = 0.0
    month = values[headers.index("Month")] if "Month" in headers else datetime.now().strftime("%Y-%m")
    return d, month


def write_budgets(sh, budgets_dict, month=None):
    ws = sh.worksheet(BUDGET_SHEET)
    headers = ws.row_values(1)
    # prepare row aligned with headers
    row = []
    for h in headers:
        if h in budgets_dict:
            row.append(budgets_dict[h])
        elif h=="Month":
            row.append(month or datetime.now().strftime("%Y-%m"))
        elif h=="Updated":
            row.append(datetime.now().isoformat())
        else:
            row.append(0)
    # clear existing rows 2.. and add new one
    ws.resize(rows=2)
    ws.delete_rows(2)
    ws.append_row(row)


def read_expenses(sh, sheet_name):
    ws = sh.worksheet(sheet_name)
    df = pd.DataFrame(ws.get_all_records())
    if df.empty:
        return df
    # ensure Amount numeric
    df["Amount"] = pd.to_numeric(df["Amount"], errors='coerce').fillna(0.0)
    return df


def append_expense(sh, sheet_name, description, amount):
    ws = sh.worksheet(sheet_name)
    ts = datetime.now().isoformat(sep=' ', timespec='seconds')
    ws.append_row([ts, description, amount], value_input_option='USER_ENTERED')


def clear_expenses(sh, sheet_name):
    ws = sh.worksheet(sheet_name)
    # clear all but header
    ws.clear()
    ws.append_row(["Timestamp","Description","Amount"])    

# ----------------- BUSINESS LOGIC -----------------

st.set_page_config(page_title="מנהל הוצאות ביתי", layout="centered")
sh = get_gspread_client()
ensure_sheets(sh)

budgets, current_month = read_budgets(sh)

PAGES = ["הגדרת תקציב שבועי"] + WEEK_SHEETS + ["הוצאות שונות","סיכומים והגדרות"]
page = st.sidebar.radio("עמודים", PAGES)

# ---------- Page: Budget setup ----------
if page == "הגדרת תקציב שבועי":
    st.header("הגדרת תקציב שבועי (5 שבועות)")
    with st.form("budget_form"):
        cols = st.columns(2)
        new_budgets = {}
        for i in range(5):
            with cols[i%2]:
                v = st.number_input(f"תקציב שבוע {i+1}", min_value=0.0, value=float(budgets.get(f"Week{i+1}",0.0)), step=10.0, format="%.2f")
                new_budgets[f"Week{i+1}"] = v
        misc = st.number_input("תקציב להוצאות שונות", min_value=0.0, value=float(budgets.get("Misc_Budget",0.0)), step=10.0, format="%.2f")
        new_budgets["Misc_Budget"] = misc
        submitted = st.form_submit_button("שמור תקציבים")
        if submitted:
            write_budgets(sh, new_budgets)
            st.success("תקציבים נשמרו בהצלחה")

# ---------- Pages: Week 1-5 and Misc ----------
elif page in WEEK_SHEETS + ["הוצאות שונות"]:
    if page == "הוצאות שונות":
        sheet_name = MISC_SHEET
    else:
        sheet_name = page
    st.header(f"הזנת הוצאות — {sheet_name}")
    df = read_expenses(sh, sheet_name)
    week_budget_key = None
    if sheet_name.startswith("Week"):
        week_budget_key = sheet_name
    # show remaining budget
    week_budget = budgets.get(week_budget_key, 0.0) if week_budget_key else budgets.get("Misc_Budget",0.0)
    total_spent = float(df["Amount"].sum()) if not df.empty else 0.0
    remaining = week_budget - total_spent
    st.metric(label="יתרת שבוע/קטגוריה", value=f"{remaining:.2f}", delta=f"{ -total_spent:.2f}")

    with st.form("expense_form"):
        desc = st.text_input("פירוט הוצאה")
        amt = st.number_input("סכום", min_value=0.0, step=1.0, format="%.2f")
        add = st.form_submit_button("הוספת הוצאה")
        if add:
            if not desc:
                st.error("יש להזין פירוט עבור ההוצאה")
            else:
                append_expense(sh, sheet_name, desc, amt)
                st.success("הוצאה נוספה")
                st.experimental_rerun()

    st.subheader("טבלת הוצאות")
    if df.empty:
        st.info("טרם הוזנו הוצאות")
    else:
        st.dataframe(df.sort_values(by="Timestamp", ascending=False).reset_index(drop=True))

# ---------- Page: Summary & Settings ----------
elif page == "סיכומים והגדרות":
    st.header("סיכומים והגדרות")
    st.subheader(datetime.now().strftime("%B %Y"))
    # monthly totals
    all_dfs = {name: read_expenses(sh, name) for name in WEEK_SHEETS + [MISC_SHEET]}
    total_month_budget = sum(budgets.get(f"Week{i+1}",0.0) for i in range(5)) + budgets.get("Misc_Budget",0.0)
    total_spent = sum(df["Amount"].sum() if not df.empty else 0.0 for df in all_dfs.values())
    total_remaining = total_month_budget - total_spent
    st.metric("תקציב חודשי כולל", f"{total_month_budget:.2f}")
    st.metric("סך ההוצאות עד כה", f"{total_spent:.2f}")
    st.metric("יתרה כוללת", f"{total_remaining:.2f}")

    st.markdown("---")
    st.subheader("איפוס נתונים")
    st.write("כפתור זה יאפס את כל ההוצאות ויאפס את התקציבים. יש אישור כפול לפני ביצוע.")
    if "confirm_reset_step" not in st.session_state:
        st.session_state["confirm_reset_step"] = 0
    if st.button("התחל איפוס נתונים"):
        st.session_state["confirm_reset_step"] = 1
    if st.session_state["confirm_reset_step"] == 1:
        st.warning("האם אתה בטוח? פעולה זו תמחק את כל ההוצאות ותאפס תקציבים")
        cols = st.columns(2)
        if cols[0].button("אישור ולמחוק הכל"):
            # clear expense sheets
            for name in WEEK_SHEETS + [MISC_SHEET]:
                clear_expenses(sh, name)
            # reset budgets to zeros
            zero_budgets = {f"Week{i+1}":0 for i in range(5)}
            zero_budgets["Misc_Budget"] = 0
            write_budgets(sh, zero_budgets, month=datetime.now().strftime("%Y-%m"))
            st.success("הנתונים אופסו בהצלחה")
            st.session_state["confirm_reset_step"] = 0
        if cols[1].button("ביטול"):
            st.session_state["confirm_reset_step"] = 0

    st.markdown("---")
    st.subheader("המלצות ושיפורים")
    st.write("- הוספת קטגוריות חכמות (מזון, דלק, חשמל) עם ויזואליזציה.")
    st.write("- הוספת גרפים שבועיים / חודשי עם התראות כאשר התקציב קרוב לסיום.")
    st.write("- לתמיכה מרובה משתמשים — הוספת טבלת משתמשים וזיהוי באמצעות אימייל.")

# End of file
