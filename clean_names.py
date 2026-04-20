import re
import pandas as pd

# -----------------------------
# CLEAN FUNCTION (unchanged, still useful)
# -----------------------------
def clean_text(text):
    text = str(text)

    text = text.replace("\u00A0", " ")

    text = re.sub(
        r'[A-Za-z]\.(?:[IVXLCDM]+|\d+)(?:\.[0-9A-Za-z]+)*\.?',
        ' ',
        text
    )

    text = re.sub(r'\.\s*', ' ', text)

    text = re.sub(r'\s+', ' ', text)

    return text.strip()


# -----------------------------
# NEW: SPLIT BY CODE STRUCTURE FIRST (KEY FIX)
# -----------------------------
def split_by_codes(cell):
    text = str(cell)
    text = text.replace("\u00A0", " ")

    # SPLIT BEFORE EACH CODE
    chunks = re.split(
        r'[A-Za-z]\.(?:[IVXLCDM]+|\d+)(?:\.[0-9A-Za-z]+)*\.?',
        text
    )

    results = []
    for chunk in chunks:
        name = clean_text(chunk)
        if name:
            results.append(name)

    return results


# -----------------------------
# LOAD EXCEL
# -----------------------------
df = pd.read_excel("./data/results.xlsx", sheet_name="Results")

status_column = df.columns[0]
names_column = df.columns[1]

# -----------------------------
# APPLY NEW SPLIT LOGIC
# -----------------------------
split_names_column = df[names_column].apply(split_by_codes)

# -----------------------------
# EXPAND INTO ROWS
# -----------------------------
expanded_rows = []

for i, row in df.iterrows():
    names = split_names_column[i]

    for name in names:
        new_row = row.copy()
        new_row[names_column] = name
        expanded_rows.append(new_row)

expanded_df = pd.DataFrame(expanded_rows)

# -----------------------------
# SAVE
# -----------------------------
expanded_df.to_excel("cleaned_and_split_to_rows_output.xlsx", index=False)

print("Done: cleaned_and_split_to_rows_output.xlsx created")