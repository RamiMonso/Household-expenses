# -*- coding: utf-8 -*-
"""
streamlit_app.py
יישום ניהול הוצאות ביתיות שמתחבר ל-Google Sheets באמצעות Service Account.
תומך בשני אופני הגדרת Secrets ב-Streamlit:
1) TOML table בשם gcp_service_account (מפה של שדות)
2) JSON מלא כמחרוזת תחת המפתח gcp_service_account_json

יש להגדיר גם gsheet_key (מזהה ה-Google Spreadsheet).
"""

import json
from datetime import datetime

import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="ניהול הוצאות ביתיות", layout="centered")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# שמות גיליונות
BUDGET_SHEET = "budgets"
WEEK_SHEETS = [f"week_{i}" for i in range(1, 6)]
OTHER_SHEET = "other_expenses"


@st.cache_resource
def connect_sheet():
    """
    נרצה לתמוך ב:
    - st.secrets['gcp_service_account'] כטבלה/dict (TOML table)
    - st.secrets['gcp_service_account_json'] כמחרוזת JSON
    - st.secrets['gcp_service_account'] גם כמחרוזת JSON (למקרה שהוקלד כך)
    """
    # 1) ודא שיש gsheet_key
    gsheet_key = st.secrets.get("gsheet_key")
    if not gsheet_key:
        raise Exception("לא נמצא secret בשם 'gsheet_key'. יש להוסיף את מזהה ה-Google Sheet ב-Streamlit Secrets.")

    # 2) נסה לקבל Credentials מתוך st.secrets
    creds = None

    # א. ניסיון מתוך table/dict (TOML)
    try:
        maybe_table = st.secrets.get("gcp_service_account")
        if isinstance(maybe_table, dict):
            creds = Credentials.from_service_account_info(maybe_table, scopes=SCOPES)
    except Exception:
        creds = None

    # ב. אם לא הצלחנו, נסה לטעון מחרוזת JSON (מפתח JSON מלא)
    if creds is None:
        json_text = st.secrets.get("gcp_service_account_json") or st.secrets.get("gcp_service_account")
        if json_text:
            try:
                cred_dict = json.loads(json_text)
                creds = Credentials.from_service_account_info(cred_dict, scopes=SCOPES)
            except Exception as e:
                raise Exception("לא הצלחנו לפרסר את ה-JSON מתוך ה-secrets. ודא שה-JSON תקין. שגיאה: " + str(e))

    if creds is None:
        raise Exception("לא נמצאו הרשאות Service Account ב-st.secrets. הוסף 'gcp_service_account' (טבלה) או 'gcp_service_account_json' (מחרוזת JSON).")

    # ראה שהחיבור ל-gspread מצליח
    try:
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(gsheet_key)
    except Exception as e:
        raise Exception("שגיאה בעת פתיחת ה-Google Sheet — בדוק ש־gsheet_key נכון וששיתפת את הגיליון עם client_email של Service Account. שגיאה: " + str(e))

    return sh


# פונקציות עזר
def ensure_sheets_exist(sh):
    existing = {ws.title for ws in sh.worksheets()}

    if BUDGET_SHEET not in existing:
        sh.add_worksheet(title=BUDGET_SHEET, rows=10, cols=10)
        ws = sh.worksheet(BUDGET_SHEET)
        headers = ["month_name", "week1", "week2", "week3", "week4", "week5", "other_budget"]
        ws.append_row(headers)
        ws.append_row([datetime.now().strftime("%B %Y"), "", "", "", "", "", ""])

    for name in WEEK_SHEETS + [OTHER_SHEET]:
        if name not in existing:
            sh.add_worksheet(title=name, rows=1000, cols=4)
            ws = sh.worksheet(name)
            ws.append_row(["timestamp", "description", "amount"])


def read_budgets(sh):
    ws = sh.worksheet(BUDGET_SHEET)
    rows = ws.get_all_values()
    if len(rows) < 2:
        return {f"week{i}": 0 for i in range(1, 6)}, 0, datetime.now().strftime("%B %Y")
    headers = rows[0]
    values = rows[1]
    data = dict(zip(headers, values))
    # המרה למספרים
    weeks = {}
    for i in range(1, 6):
        raw = data.get(f"week{i}", "") or ""
        try:
            weeks[f"week{i}"] = float(raw) if raw != "" else 0.0
        except Exception:
            weeks[f"week{i}"] = 0.0
    try:
        other_budget = float(data.get("other_budget", "") or 0.0)
    except Exception:
        other_budget = 0.0
    month_name = data.get("month_name", datetime.now().strftime("%B %Y"))
    return weeks, other_budget, month_name


def update_budgets(sh, weeks_dict, other_budget, month_name=None):
    ws = sh.worksheet(BUDGET_SHEET)
    headers = ["month_name", "week1", "week2", "week3", "week4", "week5", "other_budget"]
    values = [month_name or datetime.now().strftime("%B %Y")] + [weeks_dict.get(f"week{i}", 0.0) for i in range(1, 6)] + [other_budget]
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
        return pd.DataFrame(columns=["timestamp", "description", "amount"])
    df = pd.DataFrame(rows)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    return df


def reset_all(sh):
    for name in WEEK_SHEETS + [OTHER_SHEET]:
        ws = sh.worksheet(name)
        ws.clear()
        ws.append_row(["timestamp", "description", "amount"])
    ws = sh.worksheet(BUDGET_SHEET)
    ws.clear()
    ws.append_row(["month_name", "week1", "week2", "week3", "week4", "week5", "other_budget"])
    ws.append_row([datetime.now().strftime("%B %Y"), "", "", "", "", "", ""])


# --- התחלת החיבור ---
try:
    sh = connect_sheet()
    ensure_sheets_exist(sh)
except Exception as e:
    st.error("שגיאה בחיבור לגוגל שיטס — בדוק את ה-Secrets, את שיתוף הגיליון וההרשאות.\n\n" + str(e))
    st.stop()

# ממשק ניווט בין העמודים
page = st.radio(
    "בחר עמוד:",
    ("הגדרת תקציב", "שבוע 1", "שבוע 2", "שבוע 3", "שבוע 4", "שבוע 5", "הוצאות שונות", "סיכום והגדרות"),
)

weeks, other_budget, month_name = read_budgets(sh)

# -- עמוד הגדרת תקציב --
if page == "הגדרת תקציב":
    st.header("הגדרת תקציב שבועי")
    st.write("הזן תקציב לכל אחת מחמשת השבועות (ניתן להשאיר ריק כדי לא לשנות).")
    with st.form("budget_form"):
        w1 = st.number_input("תקציב שבוע 1", value=float(weeks.get("week1", 0.0) or 0.0), min_value=0.0, step=1.0)
        w2 = st.number_input("תקציב שבוע 2", value=float(weeks.get("week2", 0.0) or 0.0), min_value=0.0, step=1.0)
        w3 = st.number_input("תקציב שבוע 3", value=float(weeks.get("week3", 0.0) or 0.0), min_value=0.0, step=1.0)
        w4 = st.number_input("תקציב שבוע 4", value=float(weeks.get("week4", 0.0) or 0.0), min_value=0.0, step=1.0)
        w5 = st.number_input("תקציב שבוע 5", value=float(weeks.get("week5", 0.0) or 0.0), min_value=0.0, step=1.0)
        ob = st.number_input("תקציב להוצאות שונות", value=float(other_budget or 0.0), min_value=0.0, step=1.0)
        mn = st.text_input("שם החודש", value=month_name)
        submit = st.form_submit_button("שמור תקציב")
        if submit:
            new_weeks = {f"week{i}": v for i, v in enumerate([w1, w2, w3, w4, w5], start=1)}
            update_budgets(sh, new_weeks, ob, mn)
            st.success("התקציב נשמר")

# -- דפי שבועות --
elif page in [f"שבוע {i}" for i in range(1, 6)]:
    idx = int(page.split()[1])
    sheet_name = f"week_{idx}"
    st.header(f"הזנת הוצאות - שבוע {idx}")
    df = read_expenses_df(sh, sheet_name)
    remaining = float(weeks.get(f"week{idx}", 0.0) or 0.0) - df["amount"].sum()
    st.subheader(f"יתרת השבוע: {remaining:.2f}")

    with st.form(f"add_expense_form_{idx}"):
        desc = st.text_input("פירוט ההוצאה")
        amt = st.number_input("סכום ששולם", min_value=0.0, step=1.0)
        add = st.form_submit_button("הוסף הוצאה")
        if add:
            append_expense(sh, sheet_name, desc, amt)
            st.experimental_rerun()

    st.markdown("---")
    st.subheader("טבלת הוצאות")
    st.dataframe(df)

# -- הוצאות שונות --
elif page == "הוצאות שונות":
    st.header("הוצאות שונות")
    df = read_expenses_df(sh, OTHER_SHEET)
    remaining = float(other_budget or 0.0) - df["amount"].sum()
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

# -- סיכום והגדרות --
elif page == "סיכום והגדרות":
    st.header(f"סיכום — {month_name}")

    total_budget = sum([float(weeks.get(f"week{i}", 0.0) or 0.0) for i in range(1, 6)]) + float(other_budget or 0.0)
    total_spent = 0.0
    for name in WEEK_SHEETS + [OTHER_SHEET]:
        d = read_expenses_df(sh, name)
        total_spent += d["amount"].sum()
    remaining_total = total_budget - total_spent

    st.metric("תקציב חודשי כולל", f"{total_budget:.2f}")
    st.metric("סך כל ההוצאות עד כה", f"{total_spent:.2f}")
    st.metric("יתרה עד סוף התקציב", f"{remaining_total:.2f}")

    st.markdown("---")
    st.subheader("כלים")

    # ניהול תהליך איפוס עם אישור מפורש (משתמשי session_state לנווט)
    if "confirm_reset_visible" not in st.session_state:
        st.session_state["confirm_reset_visible"] = False

    if st.button("איפוס כל הנתונים והגדרות"):
        st.session_state["confirm_reset_visible"] = True

    if st.session_state.get("confirm_reset_visible"):
        st.warning("שים לב: פעולה זו תמחוק את כל ההגדרות וההוצאות מהגיליון. פעולה אינה הפיכה.")
        cols = st.columns(2)
        with cols[0]:
            if st.button("אשר איפוס - מחק את כל הנתונים", key="confirm_reset"):
                try:
                    reset_all(sh)
                    st.success("הנתונים אופסו בהצלחה.")
                    st.session_state["confirm_reset_visible"] = False
                    st.experimental_rerun()
                except Exception as e:
                    st.error("שגיאה בזמן איפוס: " + str(e))
        with cols[1]:
            if st.button("בטל", key="cancel_reset"):
                st.session_state["confirm_reset_visible"] = False
                st.info("איפוס בוטל.")

    st.markdown("\n\nהערה: נתונים נשמרים בגיליון גוגל שאליו שירות ה-API של האפליקציה מורשה לגשת.")


# סוף הקובץ
