# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import io

# Define the weights for each category according to Bolivian regulations
# Make sure these sum to 1.0
weights = {
    "Auto eval": 0.05,
    "TO BE_SER": 0.05,
    "TO DECIDE_DECIDIR": 0.05,
    "TO DO_HACER": 0.40,
    "TO KNOW_SABER": 0.45
}

def clean_column_names(df):
    """Removes extra spaces and specific suffixes from column names."""
    new_columns = {}
    for col in df.columns:
        new_col = col.replace('  ', ' ').strip() # Replace double spaces and strip ends
        # Remove common Schoology suffixes if needed, adjust as necessary
        # Example: if columns are like "Assignment Name (1234567): TO KNOW_SABER (Pts)",
        # you might need more specific cleaning here based on the exact export format.
        # For now, just cleaning spaces.
        new_columns[col] = new_col
    df.rename(columns=new_columns, inplace=True)
    return df

def identify_grade_columns(df):
    """Identifies potential grade columns based on naming and data type."""
    grade_cols = []
    potential_cols = [col for col in df.columns if col not in ['Student Name', 'Student ID', 'Section']] # Exclude typical non-grade cols
    for col in potential_cols:
        # Attempt to convert column to numeric, coercing errors to NaN
        numeric_col = pd.to_numeric(df[col], errors='coerce')
        # If the column contains predominantly numbers (even after coercion), consider it a grade column
        # Adjust the threshold (e.g., 0.8) if needed, based on expected non-numeric entries
        if numeric_col.notna().sum() / len(df) > 0.8: # Check if >80% are numeric-like
             # Optional: Check if 'Pts' is in the original name if that's a reliable indicator
             # original_col_name = df.columns[list(df.columns).index(col)] # Get original name if renamed
             # if '(Pts)' in original_col_name: # Or just 'Pts' in col if not renamed extensively
             grade_cols.append(col)
             # Ensure the column is actually numeric, filling non-numeric with 0 after identification
             df[col] = pd.to_numeric(df[col], errors='coerce') # Re-apply coercion firmly
    # It's generally better to fill NaN *after* deciding how to calculate averages
    # df[grade_cols] = df[grade_cols].fillna(0) # Moved fillna inside calculate_averages for context
    return grade_cols


def calculate_averages_and_final_grade(df, grade_cols, weights):
    """
    Calculates the weighted contribution for each category and the final grade.
    Missing grades within a category for a student are treated as 0 for the average.

    Args:
        df (pd.DataFrame): The input DataFrame with student grades.
        grade_cols (list): List of columns containing numerical grades.
        weights (dict): Dictionary with category names as keys and weights as values.

    Returns:
        pd.DataFrame: DataFrame with added columns for weighted category
                      contributions and the final grade.
    """
    df_processed = df.copy()
    weighted_contribution_cols = [] # Keep track of the new weighted columns created

    # Fill NaN values with 0 in grade columns BEFORE calculating averages
    # This means missing assignments count as 0 towards the category average.
    df_processed[grade_cols] = df_processed[grade_cols].fillna(0)

    # Check if weights sum to 1 (or close to it)
    total_weight = sum(weights.values())
    if not pd.isclose(total_weight, 1.0):
        st.warning(f"Advertencia: La suma de los pesos de las categorías ({total_weight*100}%) no es 100%. La nota final podría ser inesperada.")

    for category, weight in weights.items():
        # Find columns belonging to this category within the identified grade columns
        # Use startswith for flexibility (e.g., "TO KNOW_SABER: Quiz 1")
        category_cols = [col for col in grade_cols if col.startswith(category)]

        # Define the name for the new weighted contribution column
        new_col_name = f"{category} Ponderado ({weight*100:.0f}%)"
        weighted_contribution_cols.append(new_col_name)

        if category_cols:
            # Calculate the raw average for the category for each student
            # .mean(axis=1) calculates the average across the columns for each row (student)
            raw_average = df_processed[category_cols].mean(axis=1)

            # Calculate the weighted contribution by multiplying the raw average by the weight
            weighted_contribution = raw_average * weight

            # Store the weighted contribution in the new column, rounding to 2 decimal places
            df_processed[new_col_name] = weighted_contribution.round(2)
            st.write(f"Calculando '{new_col_name}' usando columnas: {', '.join(category_cols)}") # Log which columns are used

        else:
            # If no columns are found for a category, assign 0 contribution and warn
            df_processed[new_col_name] = 0.0
            st.warning(f"Advertencia: No se encontraron columnas de calificaciones para la categoría '{category}'. Se asignó 0 a su contribución.")


    # Calculate final grade by summing the weighted contribution columns
    # Ensure all contribution columns exist before summing (handles cases where categories were missing)
    existing_contrib_cols = [col for col in weighted_contribution_cols if col in df_processed.columns]

    if existing_contrib_cols:
         # Sum the contributions across the columns for each row (student)
         df_processed['NOTA FINAL'] = df_processed[existing_contrib_cols].sum(axis=1).round(2)
    else:
         # Should not happen if weights dict is not empty, but as a safeguard
         df_processed['NOTA FINAL'] = 0.0
         st.error("Error Crítico: No se pudieron calcular las contribuciones ponderadas. La NOTA FINAL no se puede calcular.")

    # Optional: Reorder columns for better presentation
    # Identify ID/Name columns, then grade columns, then ponderado columns, then final grade
    id_cols = [col for col in df.columns if col in ['Student Name', 'Student ID', 'Section']] # Adjust if names differ
    # Keep original grade cols or drop them? Let's keep them for reference for now.
    # original_grade_cols = grade_cols
    
    # Order: ID -> Original Grades -> Ponderado -> Final
    # Make sure ponderado columns and NOTA FINAL are present
    final_cols_order = id_cols + grade_cols + [col for col in weighted_contribution_cols if col in df_processed.columns]
    if 'NOTA FINAL' in df_processed.columns:
        final_cols_order.append('NOTA FINAL')
    
    # Include any other columns not explicitly handled (e.g., non-grade info)
    other_cols = [col for col in df_processed.columns if col not in final_cols_order]
    final_cols_order = id_cols + other_cols + grade_cols + [col for col in weighted_contribution_cols if col in df_processed.columns]
    if 'NOTA FINAL' in df_processed.columns:
        final_cols_order.append('NOTA FINAL')
    
    # Ensure no duplicate columns and all original columns are included if needed
    final_cols_order = sorted(set(final_cols_order), key=lambda x: final_cols_order.index(x))
    missing_cols = [col for col in df_processed.columns if col not in final_cols_order]
    final_cols_order.extend(missing_cols)


    # Reorder the dataframe
    df_processed = df_processed[final_cols_order]


    return df_processed

def to_excel(df):
    """Exports DataFrame to Excel format in memory."""
    output = io.BytesIO()
    # Use ExcelWriter to potentially set formatting later if needed
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Notas Procesadas')
        # Optional: Add formatting here using writer.book or writer.sheets
        # workbook  = writer.book
        # worksheet = writer.sheets['Notas Procesadas']
        # Example: format = workbook.add_format({'num_format': '0.00'})
        # worksheet.set_column('C:Z', 12, format) # Apply format to relevant columns
    processed_data = output.getvalue()
    return processed_data


# --- Streamlit App UI ---
st.set_page_config(layout="wide") # Use wide layout
st.title("Procesador de Notas de Schoology para Normativa Boliviana")

st.write("""
Sube el archivo Excel exportado de Schoology (Gradebook -> Export).
Esta aplicación calculará las notas ponderadas para las dimensiones de Bolivia
(Saber, Hacer, Ser, Decidir) y la nota final.
""")

# Display weights being used
st.sidebar.title("Pesos de Categorías (%)")
for category, weight in weights.items():
    st.sidebar.write(f"- {category}: {weight*100:.0f}%")
if not pd.isclose(sum(weights.values()), 1.0):
     st.sidebar.error("¡La suma de los pesos no es 100%!")


uploaded_file = st.file_uploader("Elige un archivo Excel (.xlsx)", type="xlsx")

if uploaded_file is not None:
    try:
        # Read the uploaded file
        # Try skipping rows if header isn't immediately on the first row
        # Adjust skiprows if Schoology exports have variable header lengths
        try:
            df = pd.read_excel(uploaded_file, sheet_name=0, skiprows=0)
        except Exception as e: # Broad exception, specific parsing errors might be better
            st.warning(f"No se pudo leer la primera fila como encabezado, intentando saltar 1 fila. Error: {e}")
            df = pd.read_excel(uploaded_file, sheet_name=0, skiprows=1)

        st.success("Archivo cargado exitosamente.")
        st.write("Primeras filas del archivo original:")
        st.dataframe(df.head())

        # Clean column names
        df = clean_column_names(df)
        st.write("Columnas después de la limpieza inicial:")
        st.text(', '.join(df.columns))

        # Identify grade columns
        grade_cols = identify_grade_columns(df)

        if not grade_cols:
            st.error("No se pudieron identificar columnas de calificaciones numéricas. Verifica el formato del archivo.")
        else:
            st.write("Columnas identificadas como calificaciones:")
            st.text(', '.join(grade_cols))

            st.info("Presiona el botón para procesar las notas.")

            if st.button("Procesar Archivo"):
                with st.spinner("Calculando notas ponderadas y finales..."):
                    # Calculate averages and final grade using the modified logic
                    df_processed = calculate_averages_and_final_grade(df, grade_cols, weights)

                    st.success("¡Procesamiento completado!")
                    st.write("Notas Procesadas:")
                    # Display the dataframe with calculated contributions and final grade
                    st.dataframe(df_processed)

                    # Prepare data for download
                    excel_data = to_excel(df_processed)

                    st.download_button(
                        label="📥 Descargar Archivo Procesado (.xlsx)",
                        data=excel_data,
                        file_name=f"notas_procesadas_{uploaded_file.name}",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

    except Exception as e:
        st.error(f"Ocurrió un error al procesar el archivo: {e}")
        st.exception(e) # Shows detailed traceback for debugging
