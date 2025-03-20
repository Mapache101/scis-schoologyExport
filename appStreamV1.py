Here’s your improved Streamlit UI with a collapsible sidebar for teacher instructions. The functionality remains unchanged.  

### Enhancements:
- **Collapsible Sidebar**: Contains instructions for teachers.
- **Clean Layout**: Uses `st.sidebar.expander` for better organization.
- **File Upload Section**: Clearly labeled for ease of use.
- **Download Button**: Clearly displayed after processing.  

---

### Full Code:
```python
import streamlit as st
import pandas as pd
import re
import io
import xlsxwriter
from datetime import datetime
import math  

# Streamlit UI
st.set_page_config(page_title="Gradebook Organizer", layout="wide")

st.title("📊 Gradebook Organizer")

# Collapsible sidebar with instructions
with st.sidebar.expander("📌 Instructions for Teachers", expanded=False):
    st.markdown("""
    1. **Ensure Schoology is set to English**  
    2. Navigate to the **course** you want to export  
    3. Click on **Gradebook**  
    4. Click the **three dots** on the top-left corner and select **Export**  
    5. Choose **Gradebook as CSV**  
    6. **Upload** that CSV file to this program  
    7. Fill in the required fields  
    8. Click **Download Organized Gradebook (Excel)**  
    9. 🎉 **Enjoy!**  
    """)

# File uploader
uploaded_file = st.file_uploader("📂 Upload your Gradebook CSV file", type=["csv"])

# Input fields for teacher, subject, etc.
teacher = st.text_input("👩‍🏫 Teacher Name")
subject = st.text_input("📖 Subject")
course = st.text_input("🏫 Course")
level = st.text_input("🎓 Level")

# Process CSV file
if uploaded_file:
    df = pd.read_csv(uploaded_file)
    
    def process_data(df, teacher, subject, course, level):
        columns_to_drop = [
            "Nombre de usuario", "Username", "Promedio General",
            "Term1 - 2024", "Term1 - 2024 - AUTO EVAL TO BE_SER - Puntuación de categoría",
            "Unique User ID", "Overall", "2025"
        ]
        df.drop(columns=columns_to_drop, inplace=True, errors='ignore')

        exclusion_phrases = ["(Count in Grade)", "Category Score", "Ungraded"]
        columns_info, general_columns = [], []
        columns_to_remove = {"ID de usuario único", "ID de usuario unico"}

        for i, col in enumerate(df.columns):
            if col in columns_to_remove or any(phrase in col for phrase in exclusion_phrases):
                continue
            if "Grading Category:" in col:
                m = re.search(r'Grading Category:\s*([^,)]+)', col)
                category = m.group(1).strip() if m else "Unknown"
                base_name = col.split('(')[0].strip()
                new_name = f"{base_name} {category}".strip()
                columns_info.append({'original': col, 'new_name': new_name, 'category': category, 'seq_num': i})
            else:
                general_columns.append(col)

        name_terms = ["name", "first", "last"]
        name_columns = [col for col in general_columns if any(term in col.lower() for term in name_terms)]
        other_general = [col for col in general_columns if col not in name_columns]
        general_columns_reordered = name_columns + other_general

        sorted_coded = sorted(columns_info, key=lambda x: x['seq_num'])
        new_order = general_columns_reordered + [d['original'] for d in sorted_coded]

        df_cleaned = df[new_order].copy()
        rename_dict = {d['original']: d['new_name'] for d in columns_info}
        df_cleaned.rename(columns=rename_dict, inplace=True)

        groups = {}
        for d in columns_info:
            groups.setdefault(d['category'], []).append(d)
        group_order = sorted(groups.keys(), key=lambda cat: min(d['seq_num'] for d in groups[cat]))

        final_coded_order = []
        for cat in group_order:
            group_sorted = sorted(groups[cat], key=lambda x: x['seq_num'])
            group_names = [d['new_name'] for d in group_sorted]
            avg_col_name = f"Average {cat}"
            numeric_group = df_cleaned[group_names].apply(lambda x: pd.to_numeric(x, errors='coerce'))
            df_cleaned[avg_col_name] = numeric_group.mean(axis=1)
            final_coded_order.extend(group_names)
            final_coded_order.append(avg_col_name)

        final_order = general_columns_reordered + final_coded_order
        df_final = df_cleaned[final_order]

        weights = {
            "Auto eval": 0.05, "TO BE_SER": 0.05, "TO DECIDE_DECIDIR": 0.05,
            "TO DO_HACER": 0.40, "TO KNOW_SABER": 0.45
        }

        final_grade_col = "Final Grade"

        def compute_final_grade(row):
            weighted_sum, weight_sum = 0, 0
            for category, weight in weights.items():
                avg_col = f"Average {category}"
                if avg_col in row and pd.notna(row[avg_col]):
                    weighted_sum += row[avg_col] * weight
                    weight_sum += weight
            return math.ceil(weighted_sum / weight_sum) if weight_sum > 0 else None

        df_final[final_grade_col] = df_final.apply(compute_final_grade, axis=1)
        df_final.replace("Missing", "", inplace=True)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_final_filled = df_final.fillna('')
            df_final_filled.to_excel(writer, sheet_name='Sheet1', startrow=6, index=False)

            workbook, worksheet = writer.book, writer.sheets['Sheet1']
            header_format = workbook.add_format({'bold': True, 'border': 1, 'rotation': 90, 'shrink': True})
            avg_header_format = workbook.add_format({'bold': True, 'border': 1, 'rotation': 90, 'shrink': True, 'bg_color': '#ADD8E6'})
            final_grade_format = workbook.add_format({'border': 1, 'bg_color': '#90EE90'})
            border_format = workbook.add_format({'border': 1})

            worksheet.write('A1', "Teacher:", border_format)
            worksheet.write('B1', teacher, border_format)
            worksheet.write('A2', "Subject:", border_format)
            worksheet.write('B2', subject, border_format)
            worksheet.write('A3', "Class:", border_format)
            worksheet.write('B3', course, border_format)
            worksheet.write('A4', "Level:", border_format)
            worksheet.write('B4', level, border_format)
            worksheet.write('A5', datetime.now().strftime("%y-%m-%d"), border_format)

            for col_num, value in enumerate(df_final.columns):
                if value.startswith("Average "):
                    worksheet.write(6, col_num, value, avg_header_format)
                elif value == final_grade_col:
                    worksheet.write(6, col_num, value, final_grade_format)
                else:
                    worksheet.write(6, col_num, value, header_format)

            for idx, col_name in enumerate(df_final.columns):
                worksheet.set_column(idx, idx, 25 if any(term in col_name.lower() for term in name_terms) else 12)

        return output.getvalue()

    processed_file = process_data(df, teacher, subject, course, level)
    
    st.success("✅ File processed successfully!")
    st.download_button(
        label="📥 Download Organized Gradebook (Excel)",
        data=processed_file,
        file_name="organized_gradebook.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
```

Let me know if you want further refinements! 🚀
