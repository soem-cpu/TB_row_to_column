import io, re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="TB Row to Column Converter", layout="wide")

# Streamlit app: Expand rows -> columns by Registration_number (diagnostic version)
# Converts multiple visit rows into columns side-by-side per patient

st.title("📊 TB Row to Column Converter")
st.markdown("Convert multiple visit rows into columns side-by-side per patient (by Registration number)")

# 1️⃣ Upload file
st.subheader("📤 Step 1: Upload File")
uploaded_file = st.file_uploader("Upload your Excel or CSV file:", type=['xlsx', 'xls', 'csv'])

if uploaded_file is None:
    st.info("Please upload a file to begin")
    st.stop()

fname = uploaded_file.name
st.success(f"✅ File uploaded: {fname}")

# 2️⃣ Read file
if fname.lower().endswith(('.xls', '.xlsx')):
    df = pd.read_excel(uploaded_file)
else:
    df = pd.read_csv(uploaded_file, dtype=str)

st.subheader("📋 File Preview")
st.dataframe(df.head(), use_container_width=True)

# 3️⃣ Normalize column names (lowercase, remove extra spaces)
df.columns = df.columns.str.strip().str.lower()
st.subheader("🧾 Columns Detected")
st.write("Columns in your file:")
st.write(list(df.columns))

# 4️⃣ Flexible column detection
def find_col(possible_names):
    for name in df.columns:
        for pattern in possible_names:
            if re.search(pattern, name):
                return name
    return None

col_map = {
    "Tsp": find_col([r'\btsp\b', r'township']),
    "TB_or_TPT": find_col([r'tb', r'tpt']),
    "Registration_number": find_col([r'regist', r'reg\s*no', r'registration']),
    "Visit_date": find_col([r'visit', r'date']),
    "Sputum_Result": find_col([r'sputum']),
    "Gene_Xpert_Result": find_col([r'xpert', r'gene']),
    "Truenet_Result": find_col([r'true', r'truenet', r'truenat']),
    "Chest_X_Ray_Findings": find_col([r'chest', r'x-ray', r'xray', r'x ray']),
    "Remark": find_col([r'remark', r'comment', r'note'])
}

st.subheader("🔍 Column Mapping")
mapping_df = pd.DataFrame([(k, v) for k, v in col_map.items()], columns=["Expected", "Found"])
st.dataframe(mapping_df, use_container_width=True)

# --- Check for key columns ---
if not col_map["Registration_number"]:
    st.error("❌ 'Registration number' column not found. Please rename it close to 'Registration number'.")
    st.stop()

# 5️⃣ Rename to canonical names
rename_dict = {v: k for k, v in col_map.items() if v is not None}
df = df.rename(columns=rename_dict)

# 6️⃣ Clean + prepare
df['Registration_number'] = df['Registration_number'].astype(str).str.strip()

if "Visit_date" in df.columns:
    df["Visit_date"] = pd.to_datetime(df["Visit_date"], errors="coerce")
else:
    df["Visit_date"] = pd.NaT

df = df.sort_values(["Registration_number","Visit_date"]).reset_index(drop=True)
df["visit_no"] = df.groupby("Registration_number").cumcount() + 1

st.subheader("📊 Visits Summary")
visits_summary = df.groupby("Registration_number")["visit_no"].max().reset_index(name="Total_Visits")
st.dataframe(visits_summary, use_container_width=True)
st.write(f"**Total patients:** {len(visits_summary)} | **Total visits:** {len(df)}")

# 7️⃣ Pivot: Expand rows -> columns
value_cols = [c for c in ["Visit_date","Sputum_Result","Gene_Xpert_Result","Truenet_Result","Chest_X_Ray_Findings","Remark"] if c in df.columns]
index_cols = [c for c in ["Registration_number","Tsp","TB_or_TPT"] if c in df.columns]

pivot = df.pivot_table(
    index=index_cols,
    columns="visit_no",
    values=value_cols,
    aggfunc="first"
)

if pivot.empty:
    st.warning("⚠️ Pivot produced zero rows. That means column names didn't match correctly.")
    st.info("👉 Please check the mapping above — rename columns in your Excel to match these:\n"
            "Registration number, Visit date, Sputum Result, Gene Xpert Result, Truenet Result, Remark")
else:
    # 8️⃣ Flatten multi-index columns
    pivot.columns = [f"{a}_{b}" for a,b in pivot.columns]
    pivot = pivot.reset_index()

    # ✅ Reorder columns to show visits grouped neatly (Visit 1, Visit 2, ...)
    # Get base columns (registration info)
    base_cols = [c for c in ["Registration_number","Tsp","TB_or_TPT"] if c in pivot.columns]

    # Get all unique visit numbers
    visit_numbers = sorted({int(c.split('_')[-1]) for c in pivot.columns if '_' in c and c.split('_')[-1].isdigit()})

    # Define column order per visit
    visit_order = ["Visit_date", "Sputum_Result", "Gene_Xpert_Result", "Truenet_Result", "Chest_X_Ray_Findings", "Remark"]

    # Build the full column order dynamically
    ordered_cols = base_cols + [
        f"{prefix}_{num}" for num in visit_numbers for prefix in visit_order if f"{prefix}_{num}" in pivot.columns
    ]

    # Reorder the DataFrame
    pivot = pivot.reindex(columns=ordered_cols)

    # ✅ Format date columns
    for c in pivot.columns:
        if c.startswith("Visit_date_"):
            pivot[c] = pd.to_datetime(pivot[c], errors="coerce").dt.strftime("%Y-%m-%d")

    # 9️⃣ Add combined columns (all visits consolidated into single columns)
    reg_col = "Registration_number"  # Primary key for merging

    # determine maximum number of visits present (globally)
    max_visit = df["visit_no"].max() if "visit_no" in df.columns else 0

    def make_combined(col_name, fmt_date=False, output_name=None):
        """Return a Series indexed by registration containing comma-separated values for each visit.
        Missing entries are shown as '0'; duplicates are preserved in order."""
        if output_name is None:
            output_name = f"c_{col_name.lower()}"
        def joiner(g):
            pieces = []
            for i in range(1, max_visit + 1):
                entry = g.loc[g["visit_no"] == i, col_name]
                if entry.empty or pd.isna(entry.iloc[0]) or entry.iloc[0] == "":
                    pieces.append("0")
                else:
                    v = entry.iloc[0]
                    if fmt_date:
                        try:
                            v = pd.to_datetime(v, errors="coerce").strftime("%Y-%m-%d")
                        except Exception:
                            pass
                    pieces.append(str(v))
            return ",".join(pieces)
        return df.groupby(reg_col).apply(joiner).rename(output_name)

    # collect aggregated columns
    agg_series = []
    if "Visit_date" in df.columns:
        agg_series.append(make_combined("Visit_date", fmt_date=True, output_name="c_VD"))
    if "Sputum_Result" in df.columns:
        agg_series.append(make_combined("Sputum_Result", output_name="c_sputum_micro"))
    if "Truenet_Result" in df.columns:
        agg_series.append(make_combined("Truenet_Result", output_name="c_truenat"))
    if "Remark" in df.columns:
        agg_series.append(make_combined("Remark", output_name="c_remark"))

    if agg_series:
        agg_df = pd.concat(agg_series, axis=1).reset_index()
        pivot = pivot.merge(agg_df, on=reg_col, how="left")

    st.subheader("✅ Converted Data")
    st.dataframe(pivot, use_container_width=True)

    # Save Excel and provide download
    out_xlsx = "expanded_by_registration.xlsx"
    pivot.to_excel(out_xlsx, index=False)
    
    with open(out_xlsx, "rb") as f:
        st.download_button(
            label="📥 Download Excel File",
            data=f.read(),
            file_name=out_xlsx,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
