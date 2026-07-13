import pandas as pd

# Load dataset
df = pd.read_csv("data/yield_df.csv")

# Dataset information
print("Dataset Info")
print(df.info())

# Missing values
print("\nMissing Values")
print(df.isnull().sum())

# Remove unnecessary column
if "Unnamed: 0" in df.columns:
    df.drop(columns=["Unnamed: 0"], inplace=True)

# Remove duplicate rows
df.drop_duplicates(inplace=True)

# Statistics
print("\nStatistics")
print(df.describe())

# Save cleaned dataset
df.to_csv(
    "data/cleaned_yield_df.csv",
    index=False
)

print("\nCleaned dataset saved successfully!")



