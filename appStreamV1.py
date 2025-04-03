# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np # <--- IMPORT NUMPY HERE
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
        new_col = col.replace('  ', ' ').strip()
        new_columns[col] = new_col
    df.rename(columns=new_columns, inplace=True)
    return df

def identify_grade_columns(df):
    """Identifies potential grade columns based on naming and data type."""
    grade_cols = []
    potential_cols = [col for col in df.columns if col not in ['Student Name', 'Student ID', 'Section']] # Exclude typical non-grade cols
    for col in potential_cols:
        numeric_col = pd.to_numeric(df[col], errors='coerce')
        if numeric_col.notna().sum() / len(df) > 0.8:
             grade_cols.append(col)
             df[col] = pd.to_numeric(df[col], errors='coerce')
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
    weighted_contribution_cols = []

    df_processed[grade_cols] = df_processed[grade_cols].fillna(0)

    # Check if weights sum to 1 (or close to it) using numpy.isclose
    total_weight = sum(weights.values())
    if not np.isclose(total_weight, 1.0): # <--- CORRECTED HERE
        st.warning(f"Advertencia: La suma de los pesos de las categorías ({total_weight*100}%) no es 100%. La nota final podría ser inesperada.")

    for category, weight in weights.items():
        category_cols = [col for col in grade_cols if col.startswith(category)]
        new_col_name = f"{category} Ponderado ({weight*100:.0f}%)"
        weighted_contribution_cols.append(new_col_name)

        if category_cols:
            raw_average = df_processed[category_cols].mean(axis=1)
            weighted_contribution = raw_average * weight
            df_processed[new_col_name] = weighted_contribution.round(2)
            # st.write(f"Calculando '{new_col_name}' usando columnas: {', '.join(category_cols)}") # Optional logging
        else:
            df_processed[new_col_name] = 0.0
            st.warning(f"Advertencia: No se encontraron columnas de calificaciones para la categoría '{category}'. Se asignó 0 a su contribución.")

    existing_contrib_cols = [col for col in weighted_contribution_cols if col in df_processed.columns]

    if existing_contrib_cols:
         df_processed['NOTA FINAL'] = df_processed[existing_contrib_cols].sum(axis=1).round(2)
    else:
         df_processed['NOTA FINAL'] = 0.0
         st.error("Error Crítico: No se pudieron calcular las contribuciones ponderadas. La NOTA FINAL no se puede calcular.")

    # Reorder columns (Simplified version)
    id_cols = [col for col in df.columns if col in ['Student Name', 'Student ID', 'Section']]
    final_cols_order = id_cols + \
                       [col for col in grade_cols if col in df_processed.columns] + \
                       [col for col in weighted_contribution_cols if col in df_processed.columns]
    if 'NOTA FINAL' in df_processed.columns:
        final_cols_order.append('NOTA FINAL')

    other_cols = [col for col in df_processed.columns if col not in final_cols_order]
    final_cols_order = id_cols + other_cols + \
                       [col for col in grade_cols if col in df_processed.columns] + \
                       [col for col in weighted_contribution_cols if col in df_processed.columns]
    if 'NOTA FINAL' in df_processed.columns and 'NOTA FINAL' not in final_cols_order:
         final_cols_order.append('NOTA FINAL')
    
    # Ensure uniqueness and all columns are present
    final_cols_order = list(dict.fromkeys(final_cols_order)) # Keep order, unique
    missing_cols = [col for col in df_processed.columns if col not in final_cols_order]
    final_cols_order.extend(missing_cols)
    
    df_processed = df_processed[final_cols_order]

    return df_processed

def to_excel(df):
    """Exports DataFrame to Excel format in memory."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Notas Procesadas')
    processed_data = output.getvalue()
    return processed_data

# --- Streamlit App UI ---
st.set_page_config(layout="wide")
st.title("Procesador de Notas de Schoology para Normativa Boliviana")

st.write("""
Sube el archivo Excel exportado de Schoology (Gradebook -> Export).
Esta aplicación calculará las notas ponderadas para las dimensiones de Bolivia
(Saber, Hacer, Ser, Decidir) y la nota final.
""")

# Display weights being used in Sidebar
st.sidebar.title("Pesos de Categorías (%)")
for category, weight in weights.items():
    st.sidebar.write(f"- {category}: {weight*100:.0f}%")
# Check sum using numpy.isclose
if not np.isclose(sum(weights.values()), 1.0): # <--- CORRECTED HERE
     st.sidebar.error("¡La suma de los pesos no es 100%!")


uploaded_file = st.file_uploader("Elige un archivo Excel (.xlsx)", type="xlsx")

if uploaded_file is not None:
    try:
        try:
            df = pd.read_excel(uploaded_file, sheet_name=0, skiprows=0)
        except Exception as e:
            st.warning(f"No se pudo leer la primera fila como encabezado, intentando saltar 1 fila. Error: {e}")
            df = pd.read_excel(uploaded_file, sheet_name=0, skiprows=1)

        st.success("Archivo cargado exitosamente.")
        st.write("Primeras filas del archivo original:")
        st.dataframe(df.head())

        df = clean_column_names(df)
        # st.write("Columnas después de la limpieza inicial:") # Optional log
        # st.text(', '.join(df.columns)) # Optional log

        grade_cols = identify_grade_columns(df)

        if not grade_cols:
            st.error("No se pudieron identificar columnas de calificaciones numéricas. Verifica el formato del archivo.")
        else:
            st.write("Columnas identificadas como calificaciones:")
            st.text(', '.join(grade_cols))

            st.info("Presiona el botón para procesar las notas.")

            if st.button("Procesar Archivo"):
                with st.spinner("Calculando notas ponderadas y finales..."):
                    df_processed = calculate_averages_and_final_grade(df, grade_cols, weights)

                    st.success("¡Procesamiento completado!")
                    st.write("Notas Procesadas:")
                    st.dataframe(df_processed)

                    excel_data = to_excel(df_processed)

                    st.download_button(
                        label="📥 Descargar Archivo Procesado (.xlsx)",
                        data=excel_data,
                        file_name=f"notas_procesadas_{uploaded_file.name}",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

    except Exception as e:
        st.error(f"Ocurrió un error al procesar el archivo: {e}")
        st.exception(e)
