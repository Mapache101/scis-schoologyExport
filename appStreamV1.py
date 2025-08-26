import streamlit as st
import pandas as pd
import re
import io
import xlsxwriter
from datetime import datetime
import math

# Define weights for categories
# NOTE: Ensure these weights match the categories in your gradebook.
weights = {
    "TO BE_SER": 0.05,
    "TO DECIDE_DECIDIR": 0.05,
    "TO DO_HACER": 0.40,
    "TO KNOW_SABER": 0.45,
    "AUTO EVAL": 0.05
}

def custom_round(value):
    """
    Rounds a number to the nearest integer.
    """
    return math.floor(value + 0.5)

def process_trimester_data(df, writer, trimester, teacher, subject, course, level):
    """
    Processes and formats data for a single trimester and writes it to an Excel sheet.
    """
    try:
        # Columns to keep for this specific trimester
        trimester_prefix = f"Term{trimester}"
        general_columns = ["First Name", "Last Name", "Unique User ID"]

        # Find columns relevant to this trimester and category
        # Pattern to match columns for the current trimester, ignoring count columns
        trimester_cols_pattern = re.compile(rf'^{trimester_prefix} - .*\(Max Points:.*Grading Category:.*')
        
        columns_info = []
        for i, col in enumerate(df.columns):
            if trimester_cols_pattern.match(col):
                # Use a more robust regex to extract category and max points
                m_cat = re.search(r'Grading Category:\s*([^,)]+)', col)
                category = m_cat.group(1).strip() if m_cat else "Unknown"
                m_pts = re.search(r'Max Points:\s*([\d\.]+)', col)
                max_pts = float(m_pts.group(1)) if m_pts else None
                base_name = col.split('(')[0].strip()
                new_name = f"{base_name} ({category})".strip()
                columns_info.append({
                    'original': col,
                    'new_name': new_name,
                    'category': category,
                    'seq_num': i,
                    'max_points': max_pts
                })

        # Separate and reorder columns
        df_cleaned = df.copy()
        
        # Filter for the relevant columns and rename them
        trimester_cols = [d['original'] for d in columns_info]
        df_trimester = df_cleaned[general_columns + trimester_cols].copy()
        df_trimester.rename({d['original']: d['new_name'] for d in columns_info}, axis=1, inplace=True)

        # Handle "Missing" values and convert to numeric
        df_trimester.replace("Missing", pd.NA, inplace=True)
        for d in columns_info:
            df_trimester[d['new_name']] = pd.to_numeric(df_trimester[d['new_name']], errors='coerce')

        final_coded_cols = []
        # Group columns by category and calculate weighted averages
        groups = {}
        for d in columns_info:
            groups.setdefault(d['category'], []).append(d)
        
        group_order = sorted(groups, key=lambda cat: min(d['seq_num'] for d in groups[cat]))
        
        for cat in group_order:
            grp = sorted(groups[cat], key=lambda x: x['seq_num'])
            names = [d['new_name'] for d in grp]
            
            # Calculate earned and possible points
            earned_points = df_trimester[names].copy()
            max_points_df = pd.DataFrame(index=df_trimester.index)
            
            for d in grp:
                col = d['new_name']
                max_pts = d['max_points']
                max_points_df[col] = earned_points[col].notna().astype(float) * max_pts
                
            sum_earned = earned_points.sum(axis=1, skipna=True)
            sum_possible = max_points_df.sum(axis=1, skipna=True)
            
            # Calculate raw average and apply weight
            raw_avg = (sum_earned / sum_possible) * 100
            raw_avg.fillna(0, inplace=True)
            
            weight = weights.get(cat, None)
            
            if weight is None:
                st.warning(f"Warning: No weight found for category '{cat}' in Trimester {trimester}.")
                weighted_avg = raw_avg
            else:
                weighted_avg = raw_avg * weight

            avg_col = f"Average {cat}"
            df_trimester[avg_col] = weighted_avg
            final_coded_cols.extend(names + [avg_col])

        # Compute the final grade
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

        df_trimester["Final Grade"] = df_trimester.apply(compute_final_grade, axis=1)

        # Reorder the final DataFrame
        final_order = general_columns + final_coded_cols + ["Final Grade"]
        df_final = df_trimester[final_order]

        # Write to the Excel writer object
        df_final.to_excel(writer, f'Trimester {trimester}', startrow=6, index=False)
        wb = writer.book
        ws = writer.sheets[f'Trimester {trimester}']

        # Define formats
        header_fmt = wb.add_format({
            'bold': True, 'border': 1, 'rotation': 90,
            'shrink': True, 'text_wrap': True
        })
        avg_hdr = wb.add_format({
            'bold': True, 'border': 1, 'rotation': 90,
            'shrink': True, 'text_wrap': True, 'bg_color': '#ADD8E6'
        })
        avg_data = wb.add_format({
            'border': 1, 'bg_color': '#ADD8E6', 'num_format': '0'
        })
        final_fmt = wb.add_format({
            'bold': True, 'border': 1, 'bg_color': '#90EE90', 'num_format': '0'
        })
        b_fmt = wb.add_format({'border': 1})

        # Write metadata headers
        ws.write('A1', "Teacher:", b_fmt); ws.write('B1', teacher, b_fmt)
        ws.write('A2', "Subject:", b_fmt); ws.write('B2', subject, b_fmt)
        ws.write('A3', "Class:", b_fmt);   ws.write('B3', course, b_fmt)
        ws.write('A4', "Level:", b_fmt);   ws.write('B4', level, b_fmt)
        ws.write('A5', datetime.now().strftime("%y-%m-%d"), b_fmt)
        ws.write('C1', "Trimester:", b_fmt); ws.write('D1', trimester, b_fmt)

        # Write column headers
        for idx, col in enumerate(df_final.columns):
            fmt = header_fmt
            if col.startswith("Average "):
                fmt = avg_hdr
            elif col == "Final Grade":
                fmt = final_fmt
            ws.write(6, idx, col, fmt)
            
        # Write data rows
        avg_cols = {c for c in df_final.columns if c.startswith("Average ")}
        for col_idx, col in enumerate(df_final.columns):
            fmt = avg_data if col in avg_cols else final_fmt if col == "Final Grade" else b_fmt
            for row_offset in range(len(df_final)):
                val = df_final.iloc[row_offset, col_idx]
                excel_row = 7 + row_offset
                ws.write(excel_row, col_idx, "" if pd.isna(val) else val, fmt)

        # Set column widths
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
    
    except Exception as e:
        st.error(f"An error occurred while processing Trimester {trimester}: {e}")

def process_all_trimesters(df, teacher, subject, course, level):
    """
    Main function to process all trimesters and create a multi-sheet Excel file.
    """
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='xlsxwriter', engine_kwargs={'options': {'nan_inf_to_errors': True}}) as writer:
        # Find all unique trimester numbers in the columns
        trimester_numbers = sorted(list(set(re.findall(r'Term(\d+)\s-', " ".join(df.columns)))))
        
        if not trimester_numbers:
            st.error("Could not find any trimester data in the uploaded file.")
            return None
            
        for trimester in trimester_numbers:
            st.info(f"Processing data for Trimester {trimester}...")
            process_trimester_data(df, writer, trimester, teacher, subject, course, level)
            
    return output

# --- Streamlit App ---

st.title("📊 Schoology Gradebook Analyzer")
st.write("Upload a Schoology gradebook CSV to generate a formatted Excel report.")

uploaded_file = st.file_uploader("Upload a Schoology Gradebook CSV", type="csv")

if uploaded_file:
    try:
        df = pd.read_csv(uploaded_file)
        
        with st.form("form"):
            st.subheader("Teacher/Class Info")
            teacher = st.text_input("Teacher Name")
            subject = st.text_input("Subject")
            course = st.text_input("Class/Course Name")
            level = st.text_input("Level or Grade")
            submitted = st.form_submit_button("Generate Grade Report")

        if submitted:
            result = process_all_trimesters(df, teacher, subject, course, level)
            if result:
                st.success("✅ Grade report generated successfully!")
                st.download_button(
                    label="📥 Download Excel Report",
                    data=result.getvalue(),
                    file_name=f"{subject}_{course}_grades.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
    except Exception as e:
        st.error(f"An error occurred: {e}")
        st.write("Please check if the uploaded file is a valid Schoology gradebook CSV.")
