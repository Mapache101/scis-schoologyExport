import streamlit as st
import pandas as pd
import numpy as np
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
                    val = row[col]
                    if not pd.api.types.is_scalar(val):
                        try:
                            val = val.item()
                        except Exception:
                            val = val[0]
                    if pd.notna(val):
                        total += val
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
        engine_kwargs={'_
