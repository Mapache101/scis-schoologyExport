import streamlit as st
import pandas as pd
import re
import io
import xlsxwriter
from datetime import datetime
import math  # for floor()

# Weights per category as defined by the Bolivian law
weights = {
    "Auto eval": 0.05,
    "TO BE_SER": 0.05,
    "TO DECIDE_DECIDIR": 0.05,
    "TO DO_HACER": 0.40,
    "TO KNOW_SABER": 0.45
}

# Custom round-half-up: only .5 and above goes up; everything else rounds down
def custom_round(value):
    return math.floor(value + 0.5)

def process_data(df, teacher, subject, course, level):
    # Columns to drop
    columns_to_drop = [
        "Nombre de usuario", "Username", "Promedio General",
        "Term1 - 2024", "Term1 - 2024 - AUTO EVAL TO BE_SER - Puntuación de categoría",
        "Term1 - 2024 - TO BE_SER - Puntuación de categoría",
        "Term1 - 2024 - TO DECIDE_DECIDIR - Puntuación de categoría",
        "Term1 - 2024 - TO DO_HACER - Puntuación de categoría",
        "Term1 - 2024 - TO KNOW_SABER - Puntuación de categoría",
        "Unique User ID", "Overall", "2025", "Term1 - 2025",
        "Term2- 2025", "Term3 - 2025"
    ]
    df.drop(columns=columns_to_drop, inplace=True, errors='ignore')

    # Remove "Missing" literal and treat as blank
    df.replace("Missing", pd.NA, inplace=True)

    exclusion_phrases = ["(Count in Grade)", "Category Score", "Ungraded"]
    columns_info = []
    general_columns = []
    cols_to_remove = {"ID de usuario único", "ID de usuario unico"}

    for i, col in enumerate(df.columns):
        col = str(col)
        if col in cols_to_remove or any(ph in col for ph in exclusion_phrases):
            continue

        if "Grading Category:" in col:
            m = re.search(r'Grading Category:\s*([^,)]+)', col)
            category = m.group(1).strip() if m else "Unknown"
            base_name = col.split('(')[0].strip()
            new_name = f"{base_name} {category}".strip()
            columns_info.append({
                'original': col,
                'new_name': new_name,
                'category': category,
                'seq_num': i
            })
        else:
            general_columns.append(col)

    # Reorder so name columns come first
    name_terms = ["name", "first", "last"]
    name_cols = [c for c in general_columns if any(t in c.lower() for t in name_terms)]
    other_cols = [c for c in general_columns if c not in name_cols]
    general_reordered = name_cols + other_cols

    # Coded columns in original sequence
    sorted_coded = sorted(columns_info, key=lambda x: x['seq_num'])
    new_order = general_reordered + [d['original'] for d in sorted_coded]

    df_cleaned = df[new_order].copy()
    df_cleaned.rename({d['original']: d['new_name'] for d in columns_info}, axis=1, inplace=True)

    # Group by category
    groups = {}
    for d in columns_info:
        groups.setdefault(d['category'], []).append(d)
    group_order = sorted(groups, key=lambda cat: min(d['seq_num'] for d in groups[cat]))

    final_coded = []
    for cat in group_order:
        grp = sorted(groups[cat], key=lambda x: x['seq_num'])
        names = [d['new_name'] for d in grp]
        avg_col = f"Average {cat}"
        numeric = df_cleaned[names].apply(lambda x: pd.to_numeric(x, errors='coerce'))
        raw = numeric.mean(axis=1)
        wt = next((w for k,w in weights.items() if k.lower()==cat.lower()), None)
        df_cleaned[avg_col] = (raw * wt) if wt is not None else raw
        final_coded.extend(names + [avg_col])

    final_order = general_reordered + final_coded
    df_final = df_cleaned[final_order]

    # Compute and round only the final grade
    def compute_final_grade(row):
        total = 0
        valid = False
        for col in row.index:
            if col.startswith("Average "):
                cat = col[len("Average "):]
                if any(cat.lower()==k.lower() for k in weights):
                    val = row[col]
                    if pd.notna(val):
                        total += val
                        valid = True
        return custom_round(total) if valid else pd.NA

    df_final["Final Grade"] = df_final.apply(compute_final_grade, axis=1)

    # Export to Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter',
                        engine_kwargs={'options': {'nan_inf_to_errors': True}}) as writer:
        # We still write an initial sheet so filters/column widths work, but values will be blank in the manual loop
        df_final.to_excel(writer, 'Sheet1', startrow=6, index=False)
        wb = writer.book
        ws = writer.sheets['Sheet1']

        # Formats
        header_fmt = wb.add_format({'bold':True,'border':1,'rotation':90,'shrink':True})
        avg_hdr = wb.add_format({'bold':True,'border':1,'rotation':90,'shrink':True,'bg_color':'#ADD8E6'})
        avg_data = wb.add_format({'border':1,'bg_color':'#ADD8E6'})
        final_fmt = wb.add_format({'bold':True,'border':1,'bg_color':'#90EE90'})
        b_fmt = wb.add_format({'border':1})

        # Header info
        ws.write('A1',"Teacher:",b_fmt); ws.write('B1',teacher,b_fmt)
        ws.write('A2',"Subject:",b_fmt); ws.write('B2',subject,b_fmt)
        ws.write('A3',"Class:",b_fmt);   ws.write('B3',course,b_fmt)
        ws.write('A4',"Level:",b_fmt);   ws.write('B4',level,b_fmt)
        ws.write('A5',datetime.now().strftime("%y-%m-%d"),b_fmt)

        # Column headers
        for idx, col in enumerate(df_final.columns):
            fmt = header_fmt
            if col.startswith("Average "):
                fmt = avg_hdr
            elif col == "Final Grade":
                fmt = final_fmt
            ws.write(6, idx, col, fmt)

        # Data cells: write blank if NaN/NA, else the value
        avg_cols = {c for c in df_final.columns if c.startswith("Average ")}
        for col_idx, col in enumerate(df_final.columns):
            # choose formatting
            if col in avg_cols:
                fmt = avg_data
            elif col == "Final Grade":
                fmt = final_fmt
            else:
                fmt = b_fmt

            for row_offset in range(len(df_final)):
                val = df_final.iloc[row_offset, col_idx]
                excel_row = 7 + row_offset
                if pd.isna(val):
                    ws.write(excel_row, col_idx, "", fmt)
                else:
                    ws.write(excel_row, col_idx, val, fmt)

        # Adjust column widths
        name_terms = ["name", "first", "last"]
        for idx, col in enumerate(df_final.columns):
            if any(t in col.lower() for t in name_terms):
                ws.set_column(idx, idx, 25)
            elif col.startswith("Average "):
                ws.set_column(idx, idx, 7)
            elif col == "Final Grade":
                ws.set_column(idx, idx, 12)
            else:
                ws.set_column(idx, idx, 5)

    output.seek(0)
    return output

def main():
    st.set_page_config(page_title="Gradebook Organizer")
    st.sidebar.markdown("""
        1. **Ensure Schoology is set to English**  
        2. Navigate to the **course** you want to export  
        3. Click on **Gradebook**  
        4. Click the **three dots** on the top-right corner and select **Export**  
        5. Choose **Gradebook as CSV**  
        6. **Upload** that CSV file to this program  
        7. Fill in the required fields  
        8. Click **Download Organized Gradebook (Excel)**  
        9. 🎉 **Enjoy!**
    """)
    st.title("Griffin CSV to Excel 📊")
    teacher = st.text_input("Enter teacher's name:")
    subject = st.text_input("Enter subject area:")
    course = st.text_input("Enter class:")
    level = st.text_input("Enter level:")
    uploaded_file = st.file_uploader("Upload CSV file", type=["csv"])

    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            df.columns = df.columns.astype(str)
            output = process_data(df, teacher, subject, course, level)
            st.download_button(
                "Download Organized Gradebook (Excel)",
                data=output,
                file_name="final_cleaned_gradebook.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.success("Processing completed!")
        except Exception as e:
            st.error(f"An error occurred: {e}")

if __name__=="__main__":
    main()
