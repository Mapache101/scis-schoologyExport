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

def create_single_trimester_gradebook(df, trimester_to_keep):

    # Define the general columns to always keep
    general_columns = df.columns[:5].tolist()
    
    # Find the column index for the start of each trimester
    trimester_start_indices = {}
    for i, col in enumerate(df.columns):
        if 'Term1' in col and 'Term1' not in trimester_start_indices:
            trimester_start_indices['Term1'] = i
        if 'Term2' in col and 'Term2' not in trimester_start_indices:
            trimester_start_indices['Term2'] = i
        if 'Term3' in col and 'Term3' not in trimester_start_indices:
            trimester_start_indices['Term3'] = i

    # Check if the selected trimester exists in the file
    if trimester_to_keep not in trimester_start_indices:
        st.error(f"Could not find a starting column for {trimester_to_keep}. Please check your file format.")
        return None

    # Get the start index for the selected trimester's grades
    start_index = trimester_start_indices[trimester_to_keep]
    
    # Determine the end index of the trimester's grade columns
    end_index = None
    if trimester_to_keep == 'Term1' and 'Term2' in trimester_start_indices:
        end_index = trimester_start_indices['Term2']
    elif trimester_to_keep == 'Term2' and 'Term3' in trimester_start_indices:
        end_index = trimester_start_indices['Term3']
    elif trimester_to_keep == 'Term3':
        # If it's the last trimester, we go to the end of the DataFrame
        end_index = len(df.columns)

    if end_index is None:
        # If no end column was found, it means this is the last term in the file
        end_index = len(df.columns)

    # Slice the DataFrame to get the columns for the selected trimester's grades
    trimester_grade_columns = df.columns[start_index:end_index].tolist()
    
    # Combine general columns with the selected trimester's grade columns
    columns_to_keep = general_columns + trimester_grade_columns
            
    # Create the new DataFrame with the filtered columns
    filtered_df = df[columns_to_keep]

    return filtered_df

def process_data(df, teacher, subject, course, level, trimester_choice):
    columns_to_drop = [
        "Nombre de usuario", "Username", "Promedio General",
        "Unique User ID", "2025", "Term3 - 2025"
    ]
    df.drop(columns=columns_to_drop, inplace=True, errors='ignore')

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
            m_cat = re.search(r'Grading Category:\s*([^,)]+)', col)
            category = m_cat.group(1).strip() if m_cat else "Unknown"
            m_pts = re.search(r'Max Points:\s*([\d\.]+)', col)
            max_pts = float(m_pts.group(1)) if m_pts else None
            base_name = col.split('(')[0].strip()
            new_name = f"{base_name} {category}".strip()
            columns_info.append({
                'original': col,
                'new_name': new_name,
                'category': category,
                'seq_num': i,
                'max_points': max_pts
            })
        else:
            general_columns.append(col)

    name_terms = ["name", "first", "last"]
    name_cols = [c for c in general_columns if any(t in c.lower() for t in name_terms)]
    other_cols = [c for c in general_columns if c not in name_cols]
    general_reordered = name_cols + other_cols

    sorted_coded = sorted(columns_info, key=lambda x: x['seq_num'])
    new_order = general_reordered + [d['original'] for d in sorted_coded]

    df_cleaned = df[new_order].copy()
    df_cleaned.rename({d['original']: d['new_name'] for d in columns_info}, axis=1, inplace=True)

    groups = {}
    for d in columns_info:
        groups.setdefault(d['category'], []).append(d)
    group_order = sorted(groups, key=lambda cat: min(d['seq_num'] for d in groups[cat]))

    final_coded = []
    for cat in group_order:
        grp = sorted(groups[cat], key=lambda x: x['seq_num'])
        names = [d['new_name'] for d in grp]
        
        # --- DYNAMIC LOGIC: Use pre-calculated category score based on trimester choice ---
        category_score_col = f"{trimester_choice} - 2025 - {cat} - Category Score"
        
        raw_avg = pd.Series(dtype='float64')
        if category_score_col in df.columns:
            raw_avg = pd.to_numeric(df[category_score_col], errors='coerce')
        else:
            # Fallback for columns with no space
            category_score_col_no_space = f"{trimester_choice}- 2025 - {cat} - Category Score"
            if category_score_col_no_space in df.columns:
                raw_avg = pd.to_numeric(df[category_score_col_no_space], errors='coerce')
            else:
                numeric = df_cleaned[names].apply(pd.to_numeric, errors='coerce')
                sum_earned = numeric.sum(axis=1, skipna=True)
                max_points_df = pd.DataFrame(index=df_cleaned.index)
                for d in grp:
                    col = d['new_name']
                    max_pts = d['max_points']
                    max_points_df[col] = numeric[col].notna().astype(float) * max_pts
                sum_possible = max_points_df.sum(axis=1, skipna=True)
                raw_avg = (sum_earned / sum_possible) * 100
        
        raw_avg = raw_avg.fillna(0)
        # --- END DYNAMIC LOGIC ---
            
        wt = None
        for key in weights:
            if cat.lower() == key.lower():
                wt = weights[key]
                break
        
        weighted = raw_avg * wt if wt is not None else raw_avg
        avg_col = f"Average {cat}"
        df_cleaned[avg_col] = weighted

        final_coded.extend(names + [avg_col])

    final_order = general_reordered + final_coded
    df_final = df_cleaned[final_order]

    # --- DYNAMIC LOGIC: Use a dynamic column for final grade ---
    final_grade_col = f"{trimester_choice} - 2025"
    final_grade_col_no_space = f"{trimester_choice}- 2025"

    if final_grade_col in df.columns:
        df_final["Final Grade"] = df[final_grade_col]
    elif final_grade_col_no_space in df.columns:
        df_final["Final Grade"] = df[final_grade_col_no_space]
    else:
        df_final["Final Grade"] = pd.NA
    # --- END DYNAMIC LOGIC ---

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
    
    st.success("File uploaded successfully!")
    st.subheader("Select Trimester to Process")
    
    trimester_choice = st.selectbox(
        "Choose the trimester you want to process:",
        ("Term1", "Term2", "Term3")
    )
    
    with st.form("form"):
        st.subheader("Teacher/Class Info")
        teacher = st.text_input("Teacher Name")
        subject = st.text_input("Subject")
        course = st.text_input("Class/Course Name")
        level = st.text_input("Level or Grade")
        submitted = st.form_submit_button("Generate Grade Report")

    if submitted:
        filtered_df = create_single_trimester_gradebook(df, trimester_choice)

        if filtered_df is not None:
            result = process_data(filtered_df, teacher, subject, course, level, trimester_choice)
            st.success("✅ Grade report generated!")

            st.download_button(
                label="📥 Download Excel Report",
                data=result.getvalue(),
                file_name=f"{subject}_{course}_{trimester_choice}_grades.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
