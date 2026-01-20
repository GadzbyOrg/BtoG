import pandas as pd
from sqlalchemy import create_engine
import sys

# --- CONFIGURATION ---
STAGING_URI = "postgresql://postgres:password@localhost:5433/old_staging_db"
TARGET_URI  = "postgresql://postgres:password@localhost:5432/tyrion"

def get_data(engine):
    """EXTRACT: Read raw data from the staging database."""
    print("Extracting data...")
    query = """
        SELECT 
            last_name, first_name, is_active, family, surname, 
            campus, balance, year, password 
        FROM "users_user"
    """
    return pd.read_sql(query, engine)

def transform_data(df):
    """TRANSFORM: Clean, rename, and calculate new fields."""
    print("Transforming data...")

    # 1. Rename simple mappings
    df = df.rename(columns={
        'last_name': 'nom',
        'first_name': 'prenom',
        'is_active': 'isAsleep',
        'family': 'nums',
        'surname': 'bucque',
        'password': 'passwordHash'
    })

    # 2. Handle Text Transformations
    df['tabagnss'] = df['campus'].str.upper()

    # 3. Handle Numeric/Logic Transformations
    # Convert balance to cents safely
    df['balance'] = (df['balance'].astype(float) * 100).astype(int)
    
    df = df.dropna(subset=['year'])
    # Calculate Gadz Proms Year (e.g. 2023 -> 223)
    df['proms_year'] = df['year'] - 1800
    
    df['promss'] = df['tabagnss'] + df['proms_year'].astype(str)

    # 4. Filter: Select ONLY columns destined for the new DB
    target_columns = [
        'nom', 'prenom', 'isAsleep', 'nums', 'bucque', 
        'tabagnss', 'balance', 'promss', 'passwordHash'
    ]
    return df[target_columns].copy()

def load_data(df, engine):
    """LOAD: Insert data into the target database."""
    print(f"Loading {len(df)} records into target...")
    df.to_sql('users', engine, if_exists='append', index=False)
    print("✅ Migration success!")

def main():
    try:
        # Create Engines
        staging_engine = create_engine(STAGING_URI)
        target_engine = create_engine(TARGET_URI)

        # Execute ETL Pipeline
        df_raw = get_data(staging_engine)
        df_clean = transform_data(df_raw)
        load_data(df_clean, target_engine)

    except Exception as e:
        print("\n MIGRATION FAILED")
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()