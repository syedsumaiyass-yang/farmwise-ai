import pandas as pd

DATA_PATH = "data/cleaned_yield_df.csv"

def load_data():
    df = pd.read_csv(DATA_PATH)
    return df
