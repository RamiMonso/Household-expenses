# streamlit_app.py
# דרוש התקנות: streamlit, pandas, gspread, google-auth
# pip install streamlit pandas gspread google-auth

import streamlit as st
import pandas as pd
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread
import json
import io

# ---------- CONFIG ----------
# שמור ב-Streamlit Secrets:
# st.secrets["gcp_service_account"] -> מפתח ה-service account כ-object (ראו הוראות למטה)
# st.secrets["SPREADSHEET_ID"] -> id של ה-Google Sheet
# --------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# ---------- Google Sheets helpers ----------
@st.cache_resource(show_spinner=False)
# --- החלף את init_gs() בקוד זה --- (DEBUG-וגמיש)
import json
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def init_gs_debug():
    st.write("DEBUG: בודק st.secrets...")
    try:
        keys = list(st.secrets.keys())
        st.write("DEBUG: מפתחות שנמצאים ב-st.secrets (רק שמות):", keys)
    except Exception as e:
        st.error("st.secrets אינו זמין או ריק. ודא שהכנסת את ה-Secrets לאותה אפליקציה ב-Streamlit Cloud.")
        st.stop()

    # האם יש SPREADSHEET_ID?
    if "SPREADSHEET_ID" not in st.secrets:
        st.error("SPREADSHEET_ID לא נמצא ב-st.secrets. ודא שהכנסת את מזהה הגיליון (רק ה-ID).")
        st.stop()
    else:
        st.write("SPREADSHEET_ID נמצא (לא נחשף כאן).")

    # נסה לקרוא את ה-service account בצורות שונות:
    creds_info = None
    # 1) האם הכנסת מילון בשם gcp_service_account ?
    if "gcp_service_account" in st.secrets:
        candidate = st.secrets["gcp_service_account"]
        if isinstance(candidate, str):
            st.write("gcp_service_account נמצא אך הוא מחרוזת (כנראה JSON) — אנסה להמיר באמצעות json.loads...")
            try:
                creds_info = json.loads(candidate)
                st.write("המרת מחרוזת ל־JSON הצליחה.")
            except Exception as e:
                st.error("לא הצלחנו לפענח את ה־gcp_service_account כמחרוזת JSON. אם הדבקת את ה-JSON כמחרוזת, בדוק את הפורמט או השתמש ב-gcp_service_account_json.")
                st.stop()
        elif isinstance(candidate, dict):
            st.write("gcp_service_account נמצא כמבנה (dict) — פורמט טוב.")
            creds_info = candidate
        else:
            st.error(f"gcp_service_account קיים אבל מסוג לא נתמך: {type(candidate)}")
            st.stop()

    # 2) אם לא — האם הכנסת את כל ה־JSON תחת מפתח אחר כמו gcp_service_account_json ?
    elif "gcp_service_account_json" in st.secrets:
        st.write("נמצא key בשם gcp_service_account_json — אנסה לטעון JSON ממנו.")
        raw = st.secrets["gcp_service_account_json"]
        try:
            creds_info = json.loads(raw)
            st.write("המרת gcp_service_account_json ל־JSON הצליחה.")
        except Exception as e:
            st.error("לא הצלחנו לפענח את gcp_service_account_json כ־JSON. ודא שהדבקת את תוכן הקובץ JSON במלואו (כולל שורות ה-private_key).")
            st.stop()
    else:
        st.error("לא נמצא מפתח service account ב-st.secrets בשם gcp_service_account או gcp_service_account_json.")
        st.stop()

    # לבדוק שדות מינימום בקובץ ה־creds (בלי להדפיס ערכים סודיים)
    required_fields = ["client_email", "private_key", "project_id"]
    missing = [f for f in required_fields if f not in creds_info]
    if missing:
        st.error(f"חסרים שדות חיוניים ב-creds: {missing}. ודא שהדבקת את ה-service account ה-JSON המלא.")
        st.stop()
    else:
        st.write("creds מכיל את שדות המינימום (client_email, private_key, project_id).")

    # ניסיון לבנות Credentials ולהתחבר
    try:
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    except Exception as e:
        st.error("שגיאה ביצירת Credentials.from_service_account_info — כנראה ה-private_key לא בפורמט הנכון. וודא שהשדה private_key כולל את כל שורות המפתח (-----BEGIN PRIVATE KEY----- ...).")
        st.write("שגיאת מערכת (קוד):", str(e))
        st.stop()

    try:
        client = gspread.authorize(creds)
    except Exception as e:
        st.error("שגיאה בהרשאת gspread (gspread.authorize) — ייתכן שהמפתחות לא תקינים או שיש בעיה ברשת/הרשאות.")
        st.write("שגיאת מערכת (קוד):", str(e))
        st.stop()

    # נסה לפתוח את ה-Spreadsheet
    sheet_id = st.secrets["SPREADSHEET_ID"]
    try:
        sh = client.open_by_key(sheet_id)
        st.success("חיבור ל-Google Sheets הצליח — גיליון נפתח בהצלחה.")
        return sh
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("גיליון לא נמצא עם ה-SPREADSHEET_ID שסיפקת. ודא שה-SPREADSHEET_ID נכון וששיתפת את הגיליון עם כתובת ה-service account (client_email).")
        # הדפס את הכתובת של ה-service account (למשל לצורך שיתוף) — לא חושף פרטי private_key
        st.write("כתובת Service account (לשיתוף בגיליון):", creds_info.get("client_email", "<לא זמין>"))
        st.stop()
    except Exception as e:
        st.error("שגיאה בפתיחת הגיליון — ראו קוד השגיאה למטה.")
        st.write("שגיאת מערכת (קוד):", str(e))
        st.stop()

# שימוש: במקום init_gs() תקרא init_gs_debug()
# sheet = init_gs_debug()


def ensure_worksheet(sh, name, headers):
    """מבטיח שיש גיליון בשם name עם headers (יוצר אם לא קיים). לא מוחק נתונים קיימים."""
    try:
        ws = sh.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        # צור גיליון חדש
        ws = sh.add_worksheet(title=name, rows="1000", cols=str(len(headers)))
        ws.append_row(headers, value_input_option="USER_ENTERED")
    return ws

def sheet_to_df(sh, sheet_name):
    """מחזיר DataFrame מתוך גליון; אם ריק — מחזיר df ריק עם header מתאים"""
    try:
        ws = sh.worksheet(sheet_name)
        rows = ws.get_all_records()
        if not rows:
            return pd.DataFrame(columns=ws.row_values(1) if ws.row_count>0 else [])
        return pd.DataFrame(rows)
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()

def append_row(sh, sheet_name, row_list):
    """מוסיף שורה לגליון (יוצר גליון עם header אוטומטית אם לא קיים)"""
    # אם הגיליון לא קיים — נוציא אותו עם header לפי סוג הגיליון
    # לצורך פשטות, header יוגדר כאן לפי שמות שקבענו
    headers_map = {
        "budgets": ["week", "budget"],
        "other_budget": ["key", "value"],
        "other_expenses": ["timestamp", "description", "amount"],
    }
    for i in range(1,6):
        headers_map[f"expenses_week_{i}"] = ["timestamp", "description", "amount"]

    try:
        ws = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        # צור אותו והוסף header מתאים אם ידוע
        headers = headers_map.get(sheet_name, None)
        ws = sh.add_worksheet(title=sheet_name, rows="1000", cols=str(len(row_list)))
        if headers:
            ws.append_row(headers, value_input_option="USER_ENTERED")
    ws.append_row(row_list, value_input_option="USER_ENTERED")

def overwrite_sheet_with_df(sh, sheet_name, df):
    """מוחק את תוכן הגיליון וכתב DataFrame חדש (כולל header)"""
    try:
        ws = sh.worksheet(sheet_name)
        sh.del_worksheet(ws)
    except gspread.exceptions.WorksheetNotFound:
        pass
    # צור מחדש
    rows = df.values.tolist()
    cols = list(df.columns)
    ws = sh.add_worksheet(title=sheet_name, rows=max(100, len(rows)+5), cols=max(len(cols), 3))
    ws.append_row(cols, value_input_option="USER_ENTERED")
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")

def now_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ---------- App ----------
st.set_page_config(page_title="מנהל הוצאות ביתיות", layout="centered")
st.title("מנהל הוצאות ביתיות — שמירה ב-Google Sheets")

# init google sheet
sheet = init_gs()

# Ensure core sheets exist
ensure_worksheet(sheet, "budgets", ["week", "budget"])
ensure_worksheet(sheet, "other_budget", ["key", "value"])
for i in range(1,6):
    ensure_worksheet(sheet, f"expenses_week_{i}", ["timestamp", "description", "amount"])
ensure_worksheet(sheet, "other_expenses", ["timestamp", "description", "amount"])

# Sidebar navigation
page = st.sidebar.selectbox("עמודים", [
    "הגדרת תקציב שבועי",
    "הזנת הוצאות",
    "הוצאות שונות",
    "סיכומים והגדרות"
])

# -------- Page: Budgets --------
if page == "הגדרת תקציב שבועי":
    st.header("הגדרת תקציב שבועי ל-5 שבועות")
    # קריאה מהגיליון budgets
    df_budgets = sheet_to_df(sheet, "budgets")
    # אם ריק — הכנס ברירות מחדל (0)
    if df_budgets.empty:
        data = [{"week": f"week_{i}", "budget": 0.0} for i in range(1,6)]
        df_budgets = pd.DataFrame(data)
        overwrite_sheet_with_df(sheet, "budgets", df_budgets)

    # load current budgets into dict
    budgets = {row["week"]: float(row["budget"]) for row in df_budgets.to_dict(orient="records")}

    cols = st.columns(2)
    with cols[0]:
        for i in range(1,4):
            k = f"week_{i}"
            budgets[k] = st.number_input(f"תקציב שבוע {i}", min_value=0.0, value=float(budgets.get(k, 0.0)), step=10.0, format="%.2f")
    with cols[1]:
        for i in range(4,6):
            k = f"week_{i}"
            budgets[k] = st.number_input(f"תקציב שבוע {i}", min_value=0.0, value=float(budgets.get(k, 0.0)), step=10.0, format="%.2f")

    # other budget (single value stored in other_budget sheet)
    df_other = sheet_to_df(sheet, "other_budget")
    other_val = 0.0
    if not df_other.empty:
        # assume key:value row exists as e.g. key="other_budget", value=123
        row = df_other[df_other["key"]=="other_budget"]
        if not row.empty:
            other_val = float(row.iloc[0]["value"])
    other_val = st.number_input("תקציב להוצאות שונות (חודשי)", min_value=0.0, value=float(other_val), step=10.0, format="%.2f")

    if st.button("שמור תקציבים"):
        # save budgets
        rows = [{"week": k, "budget": budgets[k]} for k in sorted(budgets.keys())]
        df_out = pd.DataFrame(rows)
        overwrite_sheet_with_df(sheet, "budgets", df_out)
        # save other budget
        df_other_out = pd.DataFrame([{"key":"other_budget", "value": other_val}])
        overwrite_sheet_with_df(sheet, "other_budget", df_other_out)
        st.success("תקציבים נשמרו לגיליון בהצלחה")

    st.markdown("---")
    st.subheader("תקציבים נוכחיים")
    display_df = pd.DataFrame([{"week": k.replace("week_","שבוע "), "budget": f"₪{v:,.2f}"} for k,v in budgets.items()])
    st.table(display_df.set_index("week"))

# -------- Page: Enter expenses per week --------
elif page == "הזנת הוצאות":
    st.header("הזנת הוצאות לפי שבוע")
    week_choice = st.selectbox("בחר שבוע", [f"expenses_week_{i}" for i in range(1,6)],
                               format_func=lambda x: x.replace("expenses_week_","שבוע "))

    st.subheader("הוספת הוצאה חדשה")
    with st.form(key=f"form_{week_choice}"):
        desc = st.text_input("פירוט ההוצאה")
        amt = st.number_input("סכום (₪)", min_value=0.0, step=1.0, format="%.2f")
        submitted = st.form_submit_button("הוסף הוצאה")
        if submitted:
            append_row(sheet, week_choice, [now_iso(), desc, float(amt)])
            st.success("הוצאה נוספה ונשמרה בגיליון")

    st.markdown("---")
    st.subheader(f"טבלת הוצאות - {week_choice.replace('expenses_week_','שבוע ')}")
    df_exp = sheet_to_df(sheet, week_choice)
    if not df_exp.empty:
        df_display = df_exp.copy()
        df_display["amount"] = df_display["amount"].astype(float).map(lambda x: f"₪{x:,.2f}")
        st.dataframe(df_display)
        csv = df_exp.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("הורד CSV (להוצאות השבוע)", data=csv, file_name=f"{week_choice}.csv", mime="text/csv")
    else:
        st.info("לא נמצאו הוצאות לשבוע זה")

    # Remaining
    df_budgets = sheet_to_df(sheet, "budgets")
    budget_map = {r["week"]: float(r["budget"]) for r in df_budgets.to_dict(orient="records")} if not df_budgets.empty else {}
    week_key = week_choice.replace("expenses_","")  # e.g. week_1
    budget = budget_map.get(week_key, 0.0)
    total_spent = df_exp["amount"].astype(float).sum() if not df_exp.empty else 0.0
    remaining = budget - total_spent
    st.metric(label="יתרת השבוע", value=f"₪{remaining:,.2f}", delta=f"₪{-total_spent:,.2f}")

# -------- Page: Other expenses --------
elif page == "הוצאות שונות":
    st.header("הוצאות שונות")
    st.subheader("הוספת הוצאה שייכת ל'הוצאות שונות'")
    with st.form(key="form_other"):
        desc = st.text_input("פירוט ההוצאה")
        amt = st.number_input("סכום (₪)", min_value=0.0, step=1.0, format="%.2f")
        submitted = st.form_submit_button("הוסף הוצאה")
        if submitted:
            append_row(sheet, "other_expenses", [now_iso(), desc, float(amt)])
            st.success("הוצאה נוספה ונשמרה בגיליון")

    st.markdown("---")
    df_exp = sheet_to_df(sheet, "other_expenses")
    if not df_exp.empty:
        df_display = df_exp.copy()
        df_display["amount"] = df_display["amount"].astype(float).map(lambda x: f"₪{x:,.2f}")
        st.dataframe(df_display)
        csv = df_exp.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("הורד CSV (הוצאות שונות)", data=csv, file_name="other_expenses.csv", mime="text/csv")
    else:
        st.info("לא נמצאו הוצאות")

    # Remaining for other budget
    df_other = sheet_to_df(sheet, "other_budget")
    other_budget = float(df_other[df_other["key"]=="other_budget"]["value"].iloc[0]) if (not df_other.empty and "value" in df_other.columns and not df_other[df_other["key"]=="other_budget"].empty) else 0.0
    total_spent = df_exp["amount"].astype(float).sum() if not df_exp.empty else 0.0
    remaining = other_budget - total_spent
    st.metric(label="יתרה להוצאות שונות", value=f"₪{remaining:,.2f}", delta=f"₪{-total_spent:,.2f}")

# -------- Page: Summary & Settings --------
elif page == "סיכומים והגדרות":
    st.header("סיכומים והגדרות")
    month_name = datetime.now().strftime('%B %Y')
    st.subheader(month_name)

    df_budgets = sheet_to_df(sheet, "budgets")
    budgets = {r["week"]: float(r["budget"]) for r in df_budgets.to_dict(orient="records")} if not df_budgets.empty else {}

    df_other = sheet_to_df(sheet, "other_budget")
    other_budget = float(df_other[df_other["key"]=="other_budget"]["value"].iloc[0]) if (not df_other.empty and "value" in df_other.columns and not df_other[df_other["key"]=="other_budget"].empty) else 0.0

    total_budget = sum(budgets.values()) + other_budget

    total_expenses = 0.0
    for i in range(1,6):
        df_exp = sheet_to_df(sheet, f"expenses_week_{i}")
        if not df_exp.empty and "amount" in df_exp.columns:
            total_expenses += df_exp["amount"].astype(float).sum()
    df_other_exp = sheet_to_df(sheet, "other_expenses")
    if not df_other_exp.empty and "amount" in df_other_exp.columns:
        total_expenses += df_other_exp["amount"].astype(float).sum()

    remaining = total_budget - total_expenses

    c1, c2, c3 = st.columns(3)
    c1.metric("תקציב כולל לחודש", f"₪{total_budget:,.2f}")
    c2.metric("סך ההוצאות עד כה", f"₪{total_expenses:,.2f}")
    c3.metric("יתרה כוללת", f"₪{remaining:,.2f}")

    st.markdown("---")
    st.subheader("ניהול נתונים")
    st.write("ניתן לייצא את כל הנתונים כקובץ JSON או לאפס את כל המידע")

    if st.button("ייצא JSON של כל הנתונים"):
        # read all sheets and bundle to a dict
        data = {}
        data["budgets"] = sheet_to_df(sheet, "budgets").to_dict(orient="records")
        for i in range(1,6):
            data[f"expenses_week_{i}"] = sheet_to_df(sheet, f"expenses_week_{i}").to_dict(orient="records")
        data["other_expenses"] = sheet_to_df(sheet, "other_expenses").to_dict(orient="records")
        data["other_budget"] = sheet_to_df(sheet, "other_budget").to_dict(orient="records")
        data_str = json.dumps(data, ensure_ascii=False, indent=2)
        st.download_button("הורד קובץ JSON", data=data_str, file_name="budget_data.json", mime="application/json")

    st.markdown("### איפוס נתונים")
    st.write("האיפוס ימחק את כל התקציבים וההוצאות. פעולה זו בלתי הפיכה ללא גיבוי.")
    confirm_text = st.text_input("אם אתה בטוח, הקלד RESET ואז לחץ 'אפס נתונים'", value="")
    if st.button("אפס נתונים"):
        if confirm_text == "RESET":
            # overwrite sheets with empty defaults
            df_budgets_empty = pd.DataFrame([{"week": f"week_{i}", "budget": 0.0} for i in range(1,6)])
            overwrite_sheet_with_df(sheet, "budgets", df_budgets_empty)
            df_other_empty = pd.DataFrame([{"key":"other_budget", "value": 0.0}])
            overwrite_sheet_with_df(sheet, "other_budget", df_other_empty)
            # clear expenses
            for i in range(1,6):
                overwrite_sheet_with_df(sheet, f"expenses_week_{i}", pd.DataFrame(columns=["timestamp","description","amount"]))
            overwrite_sheet_with_df(sheet, "other_expenses", pd.DataFrame(columns=["timestamp","description","amount"]))
            st.success("הנתונים אופסו בהצלחה")
        else:
            st.error("להגנה - הקש RESET בחלונית ואז לחץ 'אפס נתונים'")

st.markdown("---")
st.caption("אם תתקע איתי — תשלח לי הודעה ואני אעזור לך שלב-אחר-שלב.")

