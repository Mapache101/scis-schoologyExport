import streamlit as st
import pandas as pd
import re
import io
import xlsxwriter
from datetime import datetime
# import math # math.ceil is no longer used in the updated logic

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

    # Define weights for each category
    # These represent the maximum points each category contributes to the final 100
    weights = {
        "Auto eval": 5,          # Corresponds to 0.05 * 100
        "TO BE_SER": 5,          # Corresponds to 0.05 * 100
        "TO DECIDE_DECIDIR": 5,  # Corresponds to 0.05 * 100
        "TO DO_HACER": 40,       # Corresponds to 0.40 * 100
        "TO KNOW_SABER": 45       # Corresponds to 0.45 * 100
    }
    
    # --- MODIFICATION START: Calculate weighted category scores ---
    groups = {}
    for d in columns_info:
        groups.setdefault(d['category'], []).append(d)
    # Order groups by the first appearance of any column in that group.
    group_order = sorted(groups.keys(), key=lambda cat: min(d['seq_num'] for d in groups[cat] if d['category'] in weights)) # Ensure category exists in weights

    final_coded_order = []
    weighted_avg_cols = [] # Keep track of the new 'weighted average' column names

    # For each group, sort columns, calculate the simple average, then multiply by the weight.
    for cat in group_order:
        if cat not in weights: # Skip categories not defined in weights
             st.warning(f"Category '{cat}' found in data but has no defined weight. Skipping.")
             continue
             
        group_sorted = sorted(groups[cat], key=lambda x: x['seq_num'])
        group_names = [d['new_name'] for d in group_sorted]
        
        # Define the weighted average column name.
        # Changed name slightly to reflect it's not just an average but a weighted score
        weighted_avg_col_name = f"{cat} Score (Max {weights[cat]})"
        
        # Convert the group columns to numeric (coercing errors) and compute the row-wise mean.
        numeric_group = df_cleaned[group_names].apply(pd.to_numeric, errors='coerce')
        
        # Calculate the simple average (assuming scores are out of 100)
        simple_average = numeric_group.mean(axis=1) 
        
        # Calculate the weighted score for the category
        # (Simple Average / 100) * Max Points for Category == Simple Average * (Max Points / 100)
        category_weight_factor = weights[cat] / 100.0
        df_cleaned[weighted_avg_col_name] = simple_average * category_weight_factor
        
        # Append group columns and then the weighted average column.
        final_coded_order.extend(group_names)
        final_coded_order.append(weighted_avg_col_name)
        weighted_avg_cols.append(weighted_avg_col_name) # Add to list for final grade calculation
    # --- MODIFICATION END ---
        
    # Final order: general columns followed by the grouped columns (each with its weighted score).
    final_order = general_columns_reordered + final_coded_order
    df_final = df_cleaned[final_order].copy() # Use copy to ensure changes are on a new DataFrame

    # --- MODIFICATION START: Calculate final grade by summing weighted scores ---
    final_grade_col = "Final Grade (0-100)"
    
    # Sum the weighted average columns directly. Use fillna(0) to treat missing categories as 0 contribution.
    df_final[final_grade_col] = df_final[weighted_avg_cols].sum(axis=1, skipna=True)
    
    # --- MODIFICATION END ---

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
        # Apply fillna('') AFTER final grade calculation
        df_final_filled = df_final.fillna('') 
        df_final_filled.to_excel(writer, sheet_name='Sheet1', startrow=6, index=False)
        
        workbook = writer.book
        worksheet = writer.sheets['Sheet1']

        # --- FORMATTING (Adjusted for new column names/logic) ---
        header_format = workbook.add_format({
            'bold': True, 
            'border': 1,
            'rotation': 90,
            'shrink': True,
            'valign': 'vcenter' # Center align vertically
        })
        # Format for the weighted category score headers
        weighted_avg_header_format = workbook.add_format({ 
            'bold': True,
            'border': 1,
            'rotation': 90,
            'shrink': True,
            'bg_color': '#ADD8E6', # Light blue
            'valign': 'vcenter' 
        })
         # Format for the weighted category score data cells
        weighted_avg_data_format = workbook.add_format({
            'border': 1,
            'bg_color': '#ADD8E6',
            'num_format': '0.00' # Format numbers to 2 decimal places
        })
        final_grade_header_format = workbook.add_format({ # Specific format for final grade header
            'bold': True,
            'border': 1,
            #'rotation': 90, # Keep final grade horizontal
            'bg_color': '#90EE90', # Light green
            'valign': 'vcenter'
        })
        final_grade_data_format = workbook.add_format({ # Specific format for final grade data
            'bold': True,
            'border': 1,
            'bg_color': '#90EE90', # Light green
            'num_format': '0.00' # Format numbers to 2 decimal places
        })
        border_format = workbook.add_format({'border': 1})
        data_border_format = workbook.add_format({ # Format for regular data cells
             'border': 1,
             'num_format': '0.00' # Format numbers to 2 decimal places
        })


        # --- Write Metadata ---
        worksheet.write('A1', "Teacher:", border_format)
        worksheet.write('B1', teacher, border_format)
        worksheet.write('A2', "Subject:", border_format)
        worksheet.write('B2', subject, border_format)
        worksheet.write('A3', "Class:", border_format)
        worksheet.write('B3', course, border_format)
        worksheet.write('A4', "Level:", border_format)
        worksheet.write('B4', level, border_format)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M") # Use YYYY-MM-DD HH:MM for timestamp
        worksheet.write('A5', "Generated:", border_format)
        worksheet.write('B5', timestamp, border_format) # Write timestamp in B5
        
        # Set header row height for rotated text
        worksheet.set_row(6, 100) # Set height for row 7 (where headers are written)


        # Write headers with appropriate formatting
        for col_num, value in enumerate(df_final.columns):
            if value in weighted_avg_cols: # Check if it's one of the weighted score columns
                worksheet.write(6, col_num, value, weighted_avg_header_format)
            elif value == final_grade_col:
                worksheet.write(6, col_num, value, final_grade_header_format)
            else:
                worksheet.write(6, col_num, value, header_format)

        # Apply formatting to data cells
        for col_name in df_final.columns:
            col_idx = df_final.columns.get_loc(col_name)
            # Start writing data from row index 7 (Excel row 8)
            for row_idx in range(len(df_final)):
                # Get the value from the FILLED dataframe for writing
                write_value = df_final_filled.iloc[row_idx, col_idx] 
                
                excel_row = row_idx + 7 # Excel row number (starts at 1, headers are at row 7)

                if col_name in weighted_avg_cols:
                    worksheet.write(excel_row, col_idx, write_value, weighted_avg_data_format)
                elif col_name == final_grade_col:
                     worksheet.write(excel_row, col_idx, write_value, final_grade_data_format)
                else:
                    # Try converting to number if possible for regular data, otherwise write as string
                    try:
                        # Attempt conversion, apply number format if successful
                        numeric_value = float(write_value) 
                        worksheet.write_number(excel_row, col_idx, numeric_value, data_border_format)
                    except (ValueError, TypeError):
                         # If conversion fails (e.g., text), write as string with simple border
                         worksheet.write_string(excel_row, col_idx, str(write_value), border_format) 

        # Adjust column widths.
        for idx, col_name in enumerate(df_final.columns):
            if any(term in col_name.lower() for term in name_terms):
                worksheet.set_column(idx, idx, 25) # Wider for names
            elif col_name in weighted_avg_cols:
                 worksheet.set_column(idx, idx, 10) # Width for weighted score columns
            elif col_name == final_grade_col:
                worksheet.set_column(idx, idx, 12)  # Wider column for final grade
            else: # Assignment columns
                worksheet.set_column(idx, idx, 5)  # Narrower for individual assignment scores

        # --- Conditional formatting removed as direct cell formatting is now applied ---
        # num_rows = df_final.shape[0]
        # num_cols = df_final.shape[1]
        # data_start_row = 7 # Data starts at Excel row 8 (index 7)
        # data_end_row = data_start_row + num_rows -1
        # worksheet.conditional_format(data_start_row, 0, data_end_row, num_cols - 1, {
        #      'type': 'formula',
        #      'criteria': '=TRUE', # Apply to all cells
        #      'format': border_format # Apply border format
        #  })
        # --- End formatting adjustments ---

    output.seek(0)
    return output

# --- Keep the main function and imports as they were ---
def main():
    st.set_page_config(page_title="Gradebook Organizer",)
    st.title("Griffin CSV to Excel 📊")
    teacher = st.text_input("Enter teacher's name:")
    subject = st.text_input("Enter subject area:")
    course = st.text_input("Enter class:")
    level = st.text_input("Enter level:")
    uploaded_file = st.file_uploader("Upload CSV file", type=["csv"])

    if uploaded_file is not None:
        if all([teacher, subject, course, level]): # Check if all inputs are filled
            try:
                # Add encoding='utf-8' or 'latin-1' if you encounter reading errors
                df = pd.read_csv(uploaded_file) 
                output_excel = process_data(df.copy(), teacher, subject, course, level) # Pass a copy of df
                
                # Generate filename
                timestamp_file = datetime.now().strftime("%y%m%d")
                filename = f"{timestamp_file}_{teacher}_{subject}_{course}_{level}_Gradebook.xlsx"
                # Sanitize filename (remove invalid characters)
                filename = re.sub(r'[\\/*?:"<>|]', "", filename) 
                
                st.download_button(
                    label="Download Organized Gradebook (Excel)",
                    data=output_excel,
                    file_name=filename, # Use dynamic filename
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.success("Processing completed!")
            except pd.errors.ParserError as e:
                 st.error(f"Error reading CSV: {e}. Please ensure it's a valid CSV file.")
            except KeyError as e:
                 st.error(f"Error processing columns: Missing expected column structure or category '{e}'. Please check the CSV format.")
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")
                st.error("Please ensure the uploaded CSV has the expected Schoology format including 'Grading Category:' in relevant columns.")
        else:
             st.warning("Please fill in all the fields (Teacher, Subject, Class, Level) before uploading the file.")


if __name__ == "__main__":
    main()
