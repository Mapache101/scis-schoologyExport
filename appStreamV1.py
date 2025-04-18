import streamlit as st
import pandas as pd
import re
import io
import xlsxwriter
from datetime import datetime
import math  # Import the math module to use the ceil function

# Weights per category as defined by the Bolivian law
weights = {
    "Auto eval": 0.05,
    "TO BE_SER": 0.05,
    "TO DECIDE_DECIDIR": 0.05,
    "TO DO_HACER": 0.40,
    "TO KNOW_SABER": 0.45
}

def process_data(df, teacher, subject, course, level):
    # Updated list of columns to drop from the CSV (if present)
    columns_to_drop = [
        "Nombre de usuario",
        "Username",       
        "Promedio General",
        "Term1 - 2024",
        "Term1 - 2024 - AUTO EVAL TO BE_SER - Puntuación de categoría",
        "Term1 - 2024 - TO BE_SER - Puntuación de categoría",
        "Term1 - 2024 - TO DECIDE_DECIDIR - Puntuación de categoría",
        "Term1 - 2024 - TO DO_HACER - Puntuación de categoría",
        "Term1 - 2024 - TO KNOW_SABER - Puntuación de categoría",
        "Unique User ID",
        "Overall",
        "2025",
        "Term1 - 2025",
        "Term2- 2025",
        "Term3 - 2025"
    ]
    df.drop(columns=columns_to_drop, inplace=True, errors='ignore')
    
    # Define phrases that indicate the column should be excluded from the final output.
    exclusion_phrases = ["(Count in Grade)", "Category Score", "Ungraded"]
    
    # Process columns: separate those with a grading category (coded) from general ones.
    columns_info = []  # List for columns that include "Grading Category:"
    general_columns = []  # All other columns
    columns_to_remove = {"ID de usuario único", "ID de usuario unico"}

    for i, col in enumerate(df.columns):
        # Ensure we treat each header as a string.
        col = str(col)
        if col in columns_to_remove:
            continue
        # Skip columns with any exclusion phrase.
        if any(phrase in col for phrase in exclusion_phrases):
            continue

        # Check if the column header contains "Grading Category:" and process accordingly.
        if "Grading Category:" in col:
            # Extract the category using a regular expression.
            m = re.search(r'Grading Category:\s*([^,)]+)', col)
            if m:
                category = m.group(1).strip()
            else:
                category = "Unknown"
            # Use the text before any parenthesis as the base name.
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
    
    # Reorder general columns so that name-related columns appear first.
    name_terms = ["name", "first", "last"]
    name_columns = [col for col in general_columns if any(term in col.lower() for term in name_terms)]
    other_general = [col for col in general_columns if col not in name_columns]
    general_columns_reordered = name_columns + other_general

    # Order the coded columns by their original order.
    sorted_coded = sorted(columns_info, key=lambda x: x['seq_num'])
    new_order = general_columns_reordered + [d['original'] for d in sorted_coded]

    # Create a cleaned DataFrame and rename the coded columns.
    df_cleaned = df[new_order].copy()
    rename_dict = {d['original']: d['new_name'] for d in columns_info}
    df_cleaned.rename(columns=rename_dict, inplace=True)

    # Group the coded columns by the extracted grading category.
    groups = {}
    for d in columns_info:
        groups.setdefault(d['category'], []).append(d)
    # Order groups by the first appearance of any column in that group.
    group_order = sorted(groups.keys(), key=lambda cat: min(d['seq_num'] for d in groups[cat]))

    final_coded_order = []
    # For each group, sort columns by their original order and calculate a weighted average column.
    for cat in group_order:
        group_sorted = sorted(groups[cat], key=lambda x: x['seq_num'])
        group_names = [d['new_name'] for d in group_sorted]
        # Define the average column name.
        avg_col_name = f"Average {cat}"
        # Convert the group columns to numeric (coercing errors) and compute the row-wise mean.
        numeric_group = df_cleaned[group_names].apply(lambda x: pd.to_numeric(x, errors='coerce'))
        raw_avg = numeric_group.mean(axis=1)
        # Use a case-insensitive match for the weight.
        weight = next((w for k, w in weights.items() if k.lower() == cat.lower()), None)
        if weight is not None:
            df_cleaned[avg_col_name] = (raw_avg * weight).round(0)
        else:
            df_cleaned[avg_col_name] = raw_avg.round(0)
        # Append group columns and then the average column.
        final_coded_order.extend(group_names)
        final_coded_order.append(avg_col_name)
    
    # Final order: general columns followed by the grouped columns (each with its average).
    final_order = general_columns_reordered + final_coded_order
    df_final = df_cleaned[final_order]

    # Calculate the final grade by summing all the Average columns that correspond to a weighted category.
    final_grade_col = "Final Grade"
    def compute_final_grade(row):
        total = 0
        valid = False
        # Iterate over columns that start with "Average "
        for col in row.index:
            if col.startswith("Average "):
                cat = col[len("Average "):].strip()
                # Check if this average corresponds to one of the weighted categories (case-insensitive)
                if any(cat.lower() == key.lower() for key in weights):
                    total += row[col] if pd.notna(row[col]) else 0
                    valid = True
        return int(round(total)) if valid else None

    df_final[final_grade_col] = df_final.apply(compute_final_grade, axis=1)

    # Replace any occurrence of "Missing" with an empty cell.
    df_final.replace("Missing", "", inplace=True)

    # Export to Excel with formatting
    output = io.BytesIO()
    
    # Add nan_inf_to_errors option to handle NaN/INF values
    with pd.ExcelWriter(
        output, 
        engine='xlsxwriter', 
        engine_kwargs={'options': {'nan_inf_to_errors': True}}
    ) as writer:
        # Convert NaN values to empty strings before writing to Excel
        df_final_filled = df_final.fillna('')
        df_final_filled.to_excel(writer, sheet_name='Sheet1', startrow=6, index=False)
        
        workbook = writer.book
        worksheet = writer.sheets['Sheet1']

        # Create new formats
        header_format = workbook.add_format({
            'bold': True, 
            'border': 1,
            'rotation': 90,
            'shrink': True
        })
        avg_header_format = workbook.add_format({
            'bold': True,
            'border': 1,
            'rotation': 90,
            'shrink': True,
            'bg_color': '#ADD8E6'  # Light blue
        })
        avg_data_format = workbook.add_format({
            'border': 1,
            'bg_color': '#ADD8E6'
        })
        final_grade_format = workbook.add_format({
            'bold': True,
            'border': 1,
            'bg_color': '#90EE90'  # Light green
        })
        border_format = workbook.add_format({'border': 1})

        # Write header information.
        worksheet.write('A1', "Teacher:", border_format)
        worksheet.write('B1', teacher, border_format)
        worksheet.write('A2', "Subject:", border_format)
        worksheet.write('B2', subject, border_format)
        worksheet.write('A3', "Class:", border_format)
        worksheet.write('B3', course, border_format)
        worksheet.write('A4', "Level:", border_format)
        worksheet.write('B4', level, border_format)
        timestamp = datetime.now().strftime("%y-%m-%d")
        worksheet.write('A5', timestamp, border_format)

        # Write headers with appropriate formatting.
        for col_num, value in enumerate(df_final.columns):
            if value.startswith("Average "):  # Space important to avoid false matches
                worksheet.write(6, col_num, value, avg_header_format)
            elif value == final_grade_col:
                worksheet.write(6, col_num, value, final_grade_format)
            else:
                worksheet.write(6, col_num, value, header_format)

        # Apply formatting to data cells.
        average_columns = [col for col in df_final.columns if col.startswith("Average ")]
        
        for col_name in df_final.columns:
            col_idx = df_final.columns.get_loc(col_name)
            for row_idx in range(7, 7 + len(df_final)):
                value = df_final_filled.iloc[row_idx-7, col_idx]
                # If the cell value is a pandas Series, take its first element.
                if isinstance(value, pd.Series):
                    value = value.iloc[0]
                if col_name in average_columns:
                    worksheet.write(row_idx, col_idx, value, avg_data_format)
                elif col_name == final_grade_col:
                    worksheet.write(row_idx, col_idx, value, final_grade_format)
                else:
                    worksheet.write(row_idx, col_idx, value, border_format)

        # Adjust column widths.
        for idx, col_name in enumerate(df_final.columns):
            if any(term in col_name.lower() for term in ["name", "first", "last"]):
                worksheet.set_column(idx, idx, 25)
            elif col_name.startswith("Average"):
                worksheet.set_column(idx, idx, 7)
            elif col_name == final_grade_col:
                worksheet.set_column(idx, idx, 12)  # Wider column for final grade
            else:
                worksheet.set_column(idx, idx, 5)

        num_rows = df_final.shape[0]
        num_cols = df_final.shape[1]
        data_start_row = 6
        data_end_row = 6 + num_rows
        worksheet.conditional_format(data_start_row, 0, data_end_row, num_cols - 1, {
            'type': 'formula',
            'criteria': '=TRUE',
            'format': border_format
        })
    output.seek(0)
    return output

def main():
    st.set_page_config(page_title="Gradebook Organizer")
    
    # Sidebar instructions.
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
            # Convert all column headers to strings to avoid potential issues.
            df.columns = df.columns.astype(str)
            output_excel = process_data(df, teacher, subject, course, level)
            st.download_button(
                label="Download Organized Gradebook (Excel)",
                data=output_excel,
                file_name="final_cleaned_gradebook.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.success("Processing completed!")
        except Exception as e:
            st.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
