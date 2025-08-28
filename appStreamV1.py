import streamlit as st
import pandas as pd
import re
import io
import xlsxwriter
from datetime import datetime
import math

# Define weights for categories
weights = {
    "Auto eval": 0.05,
    "TO BE_SER": 0.05,
    "TO DECIDE_DECIDIR": 0.05,
    "TO DO_HACER": 0.40,
    "TO KNOW_SABER": 0.45
}

def custom_round(value):
    return math.floor(value + 0.5)

def process_data(df, teacher, subject, course, level):
    columns_to_drop = [
        "Nombre de usuario", "Username", "Promedio General",
        "Unique User ID", "2025", "Term3 - 2025"
    ]
    df.drop(columns=columns_to_drop, inplace=True, errors='ignore')

    df.replace("Missing", pd.NA, inplace=True)

    # Identify general columns (like First Name, Last Name)
    name_terms = ["name", "first", "last"]
    name_cols = [c for c in df.columns if any(t in c.lower() for t in name_terms)]
    other_cols = [c for c in df.columns if c not in name_cols and "Category Score" not in c]
    general_reordered = name_cols + other_cols
    
    # Create the final DataFrame
    df_final = df[general_reordered].copy()

    final_coded = []
    for cat, wt in weights.items():
        # Find the specific category score column name
        category_score_col = f"Term2- 2025 - {cat} - Category Score"
        
        # Check if the column exists in the DataFrame
        if category_score_col in df.columns:
            # Convert to numeric, handle potential non-numeric values
            raw_avg = pd.to_numeric(df[category_score_col], errors='coerce').fillna(0)
            
            # Apply the weight
            weighted = raw_avg * wt
            
            # Add the weighted average column to the final DataFrame
            avg_col = f"Average {cat}"
            df_final[avg_col] = weighted
            final_coded.append(avg_col)
        else:
            print(f"Warning: Category score column '{category_score_col}' not found. Skipping.")

    def compute_final_grade(row):
        total = 0
        valid = False
        for col in row.index:
            if col.startswith("Average "):
                val = row[col]
                if pd.notna(val):
                    total += val
                    valid = True
        return custom_round(total) if valid else pd.NA

    df_final["Final Grade"] = df_final.apply(compute_final_grade, axis=1)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter',
                        engine_kwargs={'options': {'nan_inf_to_errors': True}}) as writer:
        df_final.to_excel(writer, 'Sheet1', startrow=6, index=False)
        wb = writer.book
        ws = writer.sheets['Sheet1']

        header_fmt = wb.add_format({
            'bold': True,
            'border': 1,
            'rotation': 90,
            'shrink': True,
            'text_wrap': True
        })
        avg_hdr = wb.add_format({
            'bold': True,
            'border': 1,
            'rotation': 90,
            'shrink': True,
            'text_wrap': True,
            'bg_color': '#ADD8E6'
        })
        avg_data = wb.add_format({
            'border': 1,
            'bg_color': '#ADD8E6',
            'num_format': '0'
        })
        final_fmt = wb.add_format({'bold': True, 'border': 1, 'bg_color': '#90EE90'})
        b_fmt = wb.add_format({'border': 1})

        ws.write('A1', "Teacher:", b_fmt); ws.write('B1', teacher, b_fmt)
        ws.write('A2', "Subject:", b_fmt); ws.write('B2', subject, b_fmt)
        ws.write('A3', "Class:", b_fmt);    ws.write('B3', course, b_fmt)
        ws.write('A4', "Level:", b_fmt);    ws.write('B4', level, b_fmt)
        ws.write('A5', datetime.now().strftime("%y-%m-%d"), b_fmt)

        for idx, col in enumerate(df_final.columns):
            fmt = header_fmt
            if col.startswith("Average "):
                fmt = avg_hdr
            elif col == "Final Grade":
                fmt = final_fmt
            ws.write(6, idx, col, fmt)

        avg_cols = {c for c in df_final.columns if c.startswith("Average ")}
        for col_idx, col in enumerate(df_final.columns):
            fmt = avg_data if col in avg_cols else final_fmt if col == "Final Grade" else b_fmt
            for row_offset in range(len(df_final)):
                val = df_final.iloc[row_offset, col_idx]
                excel_row = 7 + row_offset
                ws.write(excel_row, col_idx, "" if pd.isna(val) else val, fmt)

        name_terms = ["name", "first", "last"]
        for idx, col in enumerate(df_final.columns):
            if any(t in col.lower() for t in name_terms):
                ws.set_column(idx, idx, 25)
            elif col.startswith("Average "):
                ws.set_column(idx, idx, 7)
            elif col == "Final Grade":
                ws.set_column(idx, idx, 12)
            else:
                ws.set_column(idx, idx, 10)

    return output

# --- Streamlit App ---

st.title("📊 Schoology Gradebook Analyzer")

uploaded_file = st.file_uploader("Upload a Schoology Gradebook CSV", type="csv")

if uploaded_file:
    df = pd.read_csv(uploaded_file)

    with st.form("form"):
        st.subheader("Teacher/Class Info")
        teacher = st.text_input("Teacher Name")
        subject = st.text_input("Subject")
        course = st.text_input("Class/Course Name")
        level = st.text_input("Level or Grade")
        submitted = st.form_submit_button("Generate Grade Report")

    if submitted:
        result = process_data(df, teacher, subject, course, level)
        st.success("✅ Grade report generated!")

        st.download_button(
            label="📥 Download Excel Report",
            data=result.getvalue(),
            file_name=f"{subject}_{course}_grades.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
