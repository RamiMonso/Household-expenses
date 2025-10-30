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
# st.secrets["gcp_service_account"] -> מפתח ה-service account כ-object או כ-string JSON
# או חלופין st.secrets["gcp_service_account_json"] -> מחרוזת JSON מלאה
# st.secrets["SPREADSHEET_ID"] -> id של ה-Google Sheet (רק ה-ID)
# --------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# --- DEBUG: בדיקת st.secrets (אין כאן הדפסת ערכים סודיים) ---
def debug_show_secrets_info():
    try:
        keys = list(st.secrets.keys())
    except Exception as e:
        st.error("st.secrets אינו זמין: " + str(e))
        return

    st.write("DEBUG: מפתחות שנמצאים ב-st.secrets (שמות בלבד):", keys)

    # בדיקה מדויקת של SPREADSHEET_ID (גם אם הוזן באותיות קטנות/גדולות)
    found_key = None
    for k in keys:
        if k.upper() == "SPREADSHEET_ID":
            found_key = k
            break

    st.write("SPREADSHEET_ID נמצא בדיוק בשם 'SPREADSHEET_ID'?", "SPREADSHEET_ID" in st.secrets)
    st.write("SPREADSHEET_ID נמצא לפי נרמול (case-insensitive)?", found_key is not None)
    if found_key:
        val = st.secrets[found_key]
        st.write("הטיפוס של הערך המאוחסן:", type(val).__name__, "| אורך המחרוזת (לא מוצג הערך):", len(str(val)))
        st.write("הערך ריק אחרי trim?", str(val).strip() == "")
    else:
        st.info("לא נמצאה מחרוזת עם שם SPREADSHEET_ID. בדוק ששמת בדיוק את המפתח 'SPREADSHEET_ID' ב-Secrets של אותה אפליקציה.")
# קריאה
debug_show_secrets_info()
# --- DEBUG VERBOSE: מציג שמות keys עם repr ו-ord כדי לגלות תווים מוסתרים ---
def debug_show_secrets_verbose():
    try:
        keys = list(st.secrets.keys())
    except Exception as e:
        st.error("st.secrets אינו זמין: " + str(e))
        return
    st.write("DEBUG: keys count =", len(keys))
    for i, k in enumerate(keys):
        st.write(f"#{i+1} key repr():", repr(k))
        # הצגת אורד (מספרים) של התווים - זה יחשוף תווי רווח/שורות בלתי נראים
        ords = [ord(ch) for ch in k]
        st.write("   chars and ords (first 50):", list(zip(list(k)[:50], ords[:50])))
        st.write("   length:", len(k))
debug_show_secrets_verbose()
# --- סוף ה-DEBUG VERBOSE ---


# ---------- Google Sheets helpers ----------
def init_gs():
    """
    מאתחל חיבור ל-Google Sheets באמצעות Service Account שנשמר ב-st.secrets.
    תומך בשני פורמטים:
      - st.secrets["gcp_service_account"] כ-TOML->dict
      - st.secrets["gcp_service_account"] כ-string JSON (יומר ל-dict)
      - או st.secrets["gcp_service_account_json"] כ-string JSON
    דורש גם st.secrets["SPREADSHEET_ID"].
    מחזיר אובייקט gspread.Spreadsheet או מפסיק את הריצה עם st.error + st.stop().
    """
    # בדוק presence של secrets
    try:
        secret_keys = list(st.secrets.keys())
    except Exception:
        st.error("st.secrets אינו זמין. ודא שאתה מריץ ב-Streamlit Cloud ושמילאת את ה-Secrets של האפליקציה.")
        st.stop()

    # SPREADSHEET_ID חובה
    if "SPREADSHEET_ID" not in st.secrets:
        st.error("SPREADSHEET_ID לא נמצא ב-st.secrets. יש להוסיף את מזהה הגיליון (רק ה-ID).")
        st.stop()

    spreadsheet_id = st.secrets["SPREADSHEET_ID"]

    # קבל creds_info מגופים שונים
    creds_info = None

    if "gcp_service_account" in st.secrets:
        candidate = st.secrets["gcp_service_account"]
        if isinstance(candidate, str):
            # כנראה הדביקו JSON כמחרוזת
            try:
                creds_info = json.loads(candidate)
            except Exception as e:
                st.error("לא ניתן לפענח את gcp_service_account כמחרוזת JSON. אם הדבקת את ה-JSON כמחרוזת, ודא שזה תקין.")
                st.write("פרט שגיאה:", str(e))
                st.stop()
        elif isinstance(candidate, dict):
            creds_info = candidate
        else:
            st.error(f"gcp_service_account נמצא אך מסוג לא נתמך: {type(candidate)}")
            st.stop()
    elif "gcp_service_account_json" in st.secrets:
        # אופציה חלופית - כל ה-JSON בתוך מחרוזת אחת
        raw = st.secrets["gcp_service_account_json"]
        try:
            creds_info = json.loads(raw)
        except Exception as e:
            st.error("לא הצלחנו לפענח את gcp_service_account_json כ-JSON. ודא שהדבקת את תוכן הקובץ JSON במלואו.")
            st.write("פרט שגיאה:", str(e))
            st.stop()
    else:
        st.error("לא נמצא מפתח service account ב-st.secrets בשם gcp_service_account או gcp_service_account_json.")
        st.stop()

    # בדיקת שדות נחוצים
    required_fields = ["client_email", "private_key", "project_id"]
    missing = [f for f in required_fields if f not in creds_info]
    if missing:
        st.error(f"חסרים שדות חיוניים ב-creds: {missing}. ודא שה-DOWNLOAD של קובץ ה-service-account JSON הושלם והודבק במלואו ב-Secrets.")
        st.stop()

    # ניסיון ליצור Credentials
    try:
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    except Exception as e:
        st.error("שגיאה ביצירת Credentials. ייתכן שה-private_key שב-Secrets לא בפורמט הנכון (שורות עם \\n חסרות).")
        st.write("פרט שגיאה:", str(e))
        st.stop()

    # ניסיון להרשאה עם gspread
    try:
        client = gspread.authorize(creds)
    except Exception as e:
        st.error("שגיאה בהרשאת gspread (gspread.authorize). בדוק את ה-Secrets, החיבור לאינטרנט והרשאות ה-API.")
        st.write("פרט שגיאה:", str(e))
        st.stop()

    # ניסיון לפתוח את ה-Spreadsheet
    try:
        sh = client.open_by_key(spreadsheet_id)
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("גיליון לא נמצא עם ה-SPREADSHEET_ID שסיפקת. ודא שה-SPREADSHEET_ID נכון וששיתפת את הגיליון עם כתובת ה-service account (client_email).")
        st.write("כתובת Service account לשיתוף:", creds_info.get("client_email", "<לא זמין>"))
        st.stop()
    except Exception as e:
        st.error("שגיאה בפתיחת ה-Google Sheet. בדוק אם ה-SPREADSHEET_ID נכון ושה-API פעיל.")
        st.write("פרט שגיאה:", str(e))
        st.stop()

    return sh


def ensure_worksheet(sh, name, headers):
    """מבטיח שיש גיליון בשם name עם headers (יוצר אם לא קיים). לא מוחק נתונים קיימים."""
    try:
        ws = sh.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=name, rows="1000", cols=str(max(1, len(headers))))
        # הוסף header אם נתון
        if headers:
            ws.append_row(headers, value_input_option="USER_ENTERED")
    return ws


def sheet_to_df(sh, sheet_name):
    """מחזיר DataFrame מתוך גליון; אם ריק — מחזיר df ריק עם header אם קיים."""
    try:
        ws = sh.worksheet(sheet_name)
        rows = ws.get_all_records()
        if not rows:
            # נסה לקבל שורת כותרת אם קיימת
            try:
                headers = ws.row_values(1)
            except Exception:
                headers = []
            return pd.DataFrame(columns=headers)
        df = pd.DataFrame(rows)
        # המרת עמודות מספריות שאמורות להיות מספרים (כמו amount, budget)
        for col in ["amount", "budget", "value"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        return df
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()
    except Exception as e:
        st.error("שגיאה בקריאת הגיליון " + sheet_name)
        st.write("פרט שגיאה:", str(e))
        return pd.DataFrame()


def append_row(sh, sheet_name, row_list):
    """מוסיף שורה לגליון (יוצר גליון עם header אוטומטית אם לא קיים)"""
    headers_map = {
        "budgets": ["week", "budget"],
        "other_budget": ["key", "value"],
        "other_expenses": ["timestamp", "description", "amount"],
    }
    for i in range(1, 6):
        headers_map[f"expenses_week_{i}"] = ["timestamp", "description", "amount"]

    try:
        ws = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        headers = headers_map.get(sheet_name, None)
        ws = sh.add_worksheet(title=sheet_name, rows="1000", cols=str(max(1, len(row_list))))
        if headers:
            ws.append_row(headers, value_input_option="USER_ENTERED")
    try:
        ws.append_row(row_list, value_input_option="USER_ENTERED")
    except Exception as e:
        st.error(f"שגיאה בהוספת שורה לגליון {sheet_name}")
        st.write("פרט שגיאה:", str(e))


def overwrite_sheet_with_df(sh, sheet_name, df):
    """
    מוחק את תוכן הגיליון הישן (אם קיים) ויוצר גיליון חדש עם תוכן DataFrame (כולל header).
    שים לב: פעולה זו מוחקת את הגיליון הישן ומחליפה אותו בגיליון חדש עם אותו שם.
    """
    try:
        ws = sh.worksheet(sheet_name)
        sh.del_worksheet(ws)
    except gspread.exceptions.WorksheetNotFound:
        pass
    # צור מחדש
    rows = df.values.tolist()
    cols = list(df.columns)
    ws = sh.add_worksheet(title=sheet_name, rows=max(100, len(rows) + 5), cols=max(len(cols), 1))
    if cols:
        ws.append_row(cols, value_input_option="USER_ENTERED")
    if rows:
        try:
            ws.append_rows(rows, value_input_option="USER_ENTERED")
        except Exception:
            # נ fallback להוספה שורה-אחר-שורה
            for r in rows:
                ws.append_row(r, value_input_option="USER_ENTERED")


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
for i in range(1, 6):
    ensure_worksheet(sheet, f"expenses_week_{i}", ["timestamp", "description", "amount"])
ensure_worksheet(sheet, "other_expenses", ["timestamp", "description", "amount"])

# Sidebar navigation
page = st.sidebar.selectbox(
    "עמודים",
    [
        "הגדרת תקציב שבועי",
        "הזנת הוצאות",
        "הוצאות שונות",
        "סיכומים והגדרות",
    ],
)

# -------- Page: Budgets --------
if page == "הגדרת תקציב שבועי":
    st.header("הגדרת תקציב שבועי ל-5 שבועות")
    df_budgets = sheet_to_df(sheet, "budgets")
    if df_budgets.empty:
        data = [{"week": f"week_{i}", "budget": 0.0} for i in range(1, 6)]
        df_budgets = pd.DataFrame(data)
        overwrite_sheet_with_df(sheet, "budgets", df_budgets)

    budgets = {row["week"]: float(row.get("budget", 0.0)) for row in df_budgets.to_dict(orient="records")}

    cols = st.columns(2)
    with cols[0]:
        for i in range(1, 4):
            k = f"week_{i}"
            budgets[k] = st.number_input(
                f"תקציב שבוע {i}",
                min_value=0.0,
                value=float(budgets.get(k, 0.0)),
                step=10.0,
                format="%.2f",
            )
    with cols[1]:
        for i in range(4, 6):
            k = f"week_{i}"
            budgets[k] = st.number_input(
                f"תקציב שבוע {i}",
                min_value=0.0,
                value=float(budgets.get(k, 0.0)),
                step=10.0,
                format="%.2f",
            )

    df_other = sheet_to_df(sheet, "other_budget")
    other_val = 0.0
    if not df_other.empty and "key" in df_other.columns and "value" in df_other.columns:
        row = df_other[df_other["key"] == "other_budget"]
        if not row.empty:
            other_val = float(row.iloc[0]["value"])
    other_val = st.number_input(
        "תקציב להוצאות שונות (חודשי)", min_value=0.0, value=float(other_val), step=10.0, format="%.2f"
    )

    if st.button("שמור תקציבים"):
        rows = [{"week": k, "budget": budgets[k]} for k in sorted(budgets.keys())]
        df_out = pd.DataFrame(rows)
        overwrite_sheet_with_df(sheet, "budgets", df_out)
        df_other_out = pd.DataFrame([{"key": "other_budget", "value": other_val}])
        overwrite_sheet_with_df(sheet, "other_budget", df_other_out)
        st.success("תקציבים נשמרו לגיליון בהצלחה")

    st.markdown("---")
    st.subheader("תקציבים נוכחיים")
    display_df = pd.DataFrame([{"week": k.replace("week_", "שבוע "), "budget": f"₪{v:,.2f}"} for k, v in budgets.items()])
    st.table(display_df.set_index("week"))

# -------- Page: Enter expenses per week --------
elif page == "הזנת הוצאות":
    st.header("הזנת הוצאות לפי שבוע")
    week_choice = st.selectbox(
        "בחר שבוע", [f"expenses_week_{i}" for i in range(1, 6)], format_func=lambda x: x.replace("expenses_week_", "שבוע ")
    )

    st.subheader("הוספת הוצאה חדשה")
    with st.form(key=f"form_{week_choice}"):
        desc = st.text_input("פירוט ההוצאה")
        amt = st.number_input("סכום (₪)", min_value=0.0, step=1.0, format="%.2f")
        submitted = st.form_submit_button("הוסף הוצאה")
        if submitted:
            append_row(sheet, week_choice, [now_iso(), desc, float(amt)])
            st.success("הוצאה נוספה ונשמרה בגיליון")

    st.markdown("---")
    st.subheader(f"טבלת הוצאות - {week_choice.replace('expenses_week_', 'שבוע ')}")
    df_exp = sheet_to_df(sheet, week_choice)
    if not df_exp.empty:
        df_display = df_exp.copy()
        if "amount" in df_display.columns:
            df_display["amount"] = df_display["amount"].astype(float).map(lambda x: f"₪{x:,.2f}")
        st.dataframe(df_display)
        csv = df_exp.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("הורד CSV (להוצאות השבוע)", data=csv, file_name=f"{week_choice}.csv", mime="text/csv")
    else:
        st.info("לא נמצאו הוצאות לשבוע זה")

    # Remaining
    df_budgets = sheet_to_df(sheet, "budgets")
    budget_map = {r["week"]: float(r.get("budget", 0.0)) for r in df_budgets.to_dict(orient="records")} if not df_budgets.empty else {}
    week_key = week_choice.replace("expenses_", "")  # e.g. week_1
    budget = budget_map.get(week_key, 0.0)
    total_spent = df_exp["amount"].astype(float).sum() if not df_exp.empty and "amount" in df_exp.columns else 0.0
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
        if "amount" in df_display.columns:
            df_display["amount"] = df_display["amount"].astype(float).map(lambda x: f"₪{x:,.2f}")
        st.dataframe(df_display)
        csv = df_exp.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("הורד CSV (הוצאות שונות)", data=csv, file_name="other_expenses.csv", mime="text/csv")
    else:
        st.info("לא נמצאו הוצאות")

    # Remaining for other budget
    df_other = sheet_to_df(sheet, "other_budget")
    other_budget = (
        float(df_other[df_other["key"] == "other_budget"]["value"].iloc[0])
        if (not df_other.empty and "value" in df_other.columns and not df_other[df_other["key"] == "other_budget"].empty)
        else 0.0
    )
    total_spent = df_exp["amount"].astype(float).sum() if not df_exp.empty and "amount" in df_exp.columns else 0.0
    remaining = other_budget - total_spent
    st.metric(label="יתרה להוצאות שונות", value=f"₪{remaining:,.2f}", delta=f"₪{-total_spent:,.2f}")

# -------- Page: Summary & Settings --------
elif page == "סיכומים והגדרות":
    st.header("סיכומים והגדרות")
    month_name = datetime.now().strftime("%B %Y")
    st.subheader(month_name)

    df_budgets = sheet_to_df(sheet, "budgets")
    budgets = {r["week"]: float(r.get("budget", 0.0)) for r in df_budgets.to_dict(orient="records")} if not df_budgets.empty else {}

    df_other = sheet_to_df(sheet, "other_budget")
    other_budget = (
        float(df_other[df_other["key"] == "other_budget"]["value"].iloc[0])
        if (not df_other.empty and "value" in df_other.columns and not df_other[df_other["key"] == "other_budget"].empty)
        else 0.0
    )

    total_budget = sum(budgets.values()) + other_budget

    total_expenses = 0.0
    for i in range(1, 6):
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
        data = {}
        data["budgets"] = sheet_to_df(sheet, "budgets").to_dict(orient="records")
        for i in range(1, 6):
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
            df_budgets_empty = pd.DataFrame([{"week": f"week_{i}", "budget": 0.0} for i in range(1, 6)])
            overwrite_sheet_with_df(sheet, "budgets", df_budgets_empty)
            df_other_empty = pd.DataFrame([{"key": "other_budget", "value": 0.0}])
            overwrite_sheet_with_df(sheet, "other_budget", df_other_empty)
            for i in range(1, 6):
                overwrite_sheet_with_df(sheet, f"expenses_week_{i}", pd.DataFrame(columns=["timestamp", "description", "amount"]))
            overwrite_sheet_with_df(sheet, "other_expenses", pd.DataFrame(columns=["timestamp", "description", "amount"]))
            st.success("הנתונים אופסו בהצלחה")
        else:
            st.error("להגנה - הקש RESET בחלונית ואז לחץ 'אפס נתונים'")

st.markdown("---")
st.caption("אם תתקע — שלח לי תמונה/העתק מה־Secrets או שורות השגיאה ואעזור מיד.")

