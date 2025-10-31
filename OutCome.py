# קבצים לפרויקט: Streamlit Home Expense Manager

להלן כל הקבצים שתצטרך להעתיק/להעלות ל- GitHub לפני פריסה ל-Streamlit Cloud. הקבצים מסומנים בקווים המפרידים ובשם הקובץ.

---

## FILE: streamlit_app.py

```python
# -*- coding: utf-8 -*-
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="ניהול הוצאות ביתיות", layout="centered")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

@st.cache_resource
def connect_sheet():
    # מחלץ את פרטי החשבון משדות הסודות של Streamlit (secrets)
    creds_info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(st.secrets["gsheet_key"])
    return sh

# שמות גליונות (worksheets)
BUDGET_SHEET = "budgets"      # גיליון שבו מאוחסנים התקציבים
WEEK_SHEETS = [f"week_{i}" for i in range(1,6)]
OTHER_SHEET = "other_expenses"

# פונקציות עזר

def ensure_sheets_exist(sh):
    # יוצר גיליונות במידת הצורך ומאתחל כותרות
    existing = {ws.title for ws in sh.worksheets()}

    if BUDGET_SHEET not in existing:
        sh.add_worksheet(title=BUDGET_SHEET, rows=10, cols=10)
        ws = sh.worksheet(BUDGET_SHEET)
        headers = ["month_name", "week1", "week2", "week3", "week4", "week5", "other_budget"]
        ws.append_row(headers)
        # ערכים ברירת מחדל (ריקים)
        ws.append_row([datetime.now().strftime("%B %Y"), "", "", "", "", "", ""])

    for name in WEEK_SHEETS + [OTHER_SHEET]:
        if name not in existing:
            sh.add_worksheet(title=name, rows=1000, cols=4)
            ws = sh.worksheet(name)
            ws.append_row(["timestamp", "description", "amount"])  # כותרות


def read_budgets(sh):
    ws = sh.worksheet(BUDGET_SHEET)
    rows = ws.get_all_values()
    if len(rows) < 2:
        return {f"week{i}": 0 for i in range(1,6)}, 0, datetime.now().strftime("%B %Y")
    headers = rows[0]
    values = rows[1]
    data = dict(zip(headers, values))
    # המרה למספרים
    weeks = {f"week{i}": float(data.get(f"week{i}", "0") or 0) for i in range(1,6)}
    other_budget = float(data.get("other_budget", "0") or 0)
    month_name = data.get("month_name", datetime.now().strftime("%B %Y"))
    return weeks, other_budget, month_name


def update_budgets(sh, weeks_dict, other_budget, month_name=None):
    ws = sh.worksheet(BUDGET_SHEET)
    headers = ["month_name", "week1", "week2", "week3", "week4", "week5", "other_budget"]
    values = [month_name or datetime.now().strftime("%B %Y")] + [weeks_dict[f"week{i}"] for i in range(1,6)] + [other_budget]
    ws.clear()
    ws.append_row(headers)
    ws.append_row(values)


def append_expense(sh, sheet_name, description, amount):
    ws = sh.worksheet(sheet_name)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws.append_row([ts, description, float(amount)])


def read_expenses_df(sh, sheet_name):
    ws = sh.worksheet(sheet_name)
    rows = ws.get_all_records()
    if not rows:
        return pd.DataFrame(columns=["timestamp","description","amount"])
    df = pd.DataFrame(rows)
    df["amount"] = pd.to_numeric(df["amount"], errors='coerce').fillna(0)
    return df


def reset_all(sh):
    # מנקה את גיליונות ההוצאות ומשחזרים כותרות
    for name in WEEK_SHEETS + [OTHER_SHEET]:
        ws = sh.worksheet(name)
        ws.clear()
        ws.append_row(["timestamp", "description", "amount"])
    # מאתחל את גיליון התקציבים
    ws = sh.worksheet(BUDGET_SHEET)
    ws.clear()
    ws.append_row(["month_name", "week1", "week2", "week3", "week4", "week5", "other_budget"])
    ws.append_row([datetime.now().strftime("%B %Y"), "", "", "", "", "", ""])


# --- התחלת החיבור ---
try:
    sh = connect_sheet()
    ensure_sheets_exist(sh)
except Exception as e:
    st.error("שגיאה בחיבור לגוגל שיטס — בדוק את הסודות וההרשאות.\n" + str(e))
    st.stop()

# ממשק ניווט בין העמודים
page = st.radio("בחר עמוד:", ("הגדרת תקציב", "שבוע 1", "שבוע 2", "שבוע 3", "שבוע 4", "שבוע 5", "הוצאות שונות", "סיכום והגדרות"))

weeks, other_budget, month_name = read_budgets(sh)

if page == "הגדרת תקציב":
    st.header("הגדרת תקציב שבועי")
    st.write("הזן תקציב לכל אחת מחמשת השבועות (ניתן להשאיר ריק כדי לא לשנות)")
    with st.form("budget_form"):
        w1 = st.number_input("תקציב שבוע 1", value=float(weeks["week1"] or 0), min_value=0.0, step=1.0)
        w2 = st.number_input("תקציב שבוע 2", value=float(weeks["week2"] or 0), min_value=0.0, step=1.0)
        w3 = st.number_input("תקציב שבוע 3", value=float(weeks["week3"] or 0), min_value=0.0, step=1.0)
        w4 = st.number_input("תקציב שבוע 4", value=float(weeks["week4"] or 0), min_value=0.0, step=1.0)
        w5 = st.number_input("תקציב שבוע 5", value=float(weeks["week5"] or 0), min_value=0.0, step=1.0)
        ob = st.number_input("תקציב להוצאות שונות", value=float(other_budget or 0), min_value=0.0, step=1.0)
        mn = st.text_input("שם החודש", value=month_name)
        submit = st.form_submit_button("שמור תקציב")
        if submit:
            new_weeks = {f"week{i}": v for i, v in enumerate([w1,w2,w3,w4,w5], start=1)}
            update_budgets(sh, new_weeks, ob, mn)
            st.success("התקציב נשמר")

elif page in [f"שבוע {i}" for i in range(1,6)]:
    idx = int(page.split()[1])
    sheet_name = f"week_{idx}"
    st.header(f"הזנת הוצאות - שבוע {idx}")
    df = read_expenses_df(sh, sheet_name)
    remaining = float(weeks[f"week{idx}"]) - df["amount"].sum()
    st.subheader(f"יתרת השבוע: {remaining:.2f}")

    with st.form("add_expense_form"):
        desc = st.text_input("פירוט ההוצאה")
        amt = st.number_input("סכום ששולם", min_value=0.0, step=1.0)
        add = st.form_submit_button("הוסף הוצאה")
        if add:
            append_expense(sh, sheet_name, desc, amt)
            st.experimental_rerun()

    st.markdown("---")
    st.subheader("טבלת הוצאות")
    st.dataframe(df)

elif page == "הוצאות שונות":
    st.header("הוצאות שונות")
    df = read_expenses_df(sh, OTHER_SHEET)
    remaining = float(other_budget) - df["amount"].sum()
    st.subheader(f"יתרת הוצאות שונות: {remaining:.2f}")
    with st.form("add_other_form"):
        desc = st.text_input("פירוט ההוצאה")
        amt = st.number_input("סכום ששולם", min_value=0.0, step=1.0)
        add = st.form_submit_button("הוסף הוצאה")
        if add:
            append_expense(sh, OTHER_SHEET, desc, amt)
            st.experimental_rerun()
    st.markdown("---")
    st.dataframe(df)

elif page == "סיכום והגדרות":
    st.header(f"סיכום — {month_name}")
    # חישובי סיכום
    total_budget = sum([float(weeks[f"week{i}"] or 0) for i in range(1,6)]) + float(other_budget or 0)
    total_spent = 0
    for name in WEEK_SHEETS + [OTHER_SHEET]:
        d = read_expenses_df(sh, name)
        total_spent += d["amount"].sum()
    remaining_total = total_budget - total_spent

    st.metric("תקציב חודשי כולל", f"{total_budget:.2f}")
    st.metric("סה""כ הוצא עד כה", f"{total_spent:.2f}")
    st.metric("יתרה עד סוף התקציב", f"{remaining_total:.2f}")

    st.markdown("---")
    st.subheader("כלים")
    if st.button("איפוס כל הנתונים והגדרות"):
        if st.confirm("האם אתה בטוח שברצונך לאפס את תקציב והוצאות? פעולה זו תמחוק את הנתונים!"):
            reset_all(sh)
            st.success("הנתונים אופסו")
            st.experimental_rerun()

    st.markdown("\n\nהערה: נתונים נשמרים בגיליון גוגל שאליו שירות ה-API של האפליקציה מורשה לגשת.")
```

---

## FILE: requirements.txt

```
streamlit>=1.20
gspread>=5.8
google-auth>=2.0
pandas
```

---

