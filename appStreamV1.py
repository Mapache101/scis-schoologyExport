import streamlit as st
import pandas as pd
import numpy as np
import xlsxwriter
from io import BytesIO

# Sidebar instructions
st.sidebar.title("Instructions")
st.sidebar.markdown("""
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

# Function to process the file
def process_gradebook(uploaded_file):
    df = pd.read_csv(uploaded_file)
    
    # User selects columns to keep
    columns_to_keep = st.multiselect("Select the columns you want to keep:", df.columns, default=list(df.columns))
    df = df[columns_to_keep]
    
    # Define category weights
    weights = {
        "Auto eval": 0.05,
        "TO BE_SER": 0.05,
        "TO DECIDE_DECIDIR": 0.05,
        "TO DO_HACER": 0.40,
        "TO KNOW_SABER": 0.45
    }
    
    # Compute weighted averages based on possible points
    for category, weight in weights.items():
        if category in df.columns:
            df[category] = df[category].fillna(0)  # Ensure no NaN values
            max_points = df[category].max()
            df[category] = (df[category] / max_points) * (weight * 100)  # Scale based on weight
    
    # Calculate final grade
    df["Final Grade"] = df[list(weights.keys())].sum(axis=1)
    df = df.round(0)  # Ensure no decimals
    
    return df

# Streamlit app
def main():
    st.title("Schoology Gradebook Formatter")
    
    uploaded_file = st.file_uploader("Upload your Schoology CSV file", type=["csv"])
    
    if uploaded_file is not None:
        df_processed = process_gradebook(uploaded_file)
        
        st.dataframe(df_processed)  # Show the processed DataFrame
        
        # Convert DataFrame to Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_processed.to_excel(writer, index=False, sheet_name='Gradebook')
            workbook = writer.book
            worksheet = writer.sheets['Gradebook']
            
            # Formatting to ensure no decimals
            format_int = workbook.add_format({'num_format': '0'})
            worksheet.set_column('A:Z', None, format_int)  # Apply formatting to all columns
            
        output.seek(0)
        
        st.download_button(
            label="Download Organized Gradebook (Excel)",
            data=output,
            file_name="organized_gradebook.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

if __name__ == "__main__":
    main()
