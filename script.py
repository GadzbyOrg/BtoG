import pandas as pd
from sqlalchemy import create_engine
import sys
import logging

# --- CONFIGURATION ---
STAGING_URI = "postgresql://postgres:password@localhost:5434/old_staging_db"
TARGET_URI  = "postgresql://postgres:password@localhost:5432/gadzby"
CLEAN_TARGET = False  # Set to True to truncate target table before loading

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def get_data(engine):
    """EXTRACT: Read raw data from the staging database."""
    logger.info("Starting extraction from staging database...")
    query = """
        SELECT 
            last_name, first_name, is_active, family, surname, 
            campus, balance, year, password, email, username, avatar
        FROM "users_user"
    """
    try:
        df = pd.read_sql(query, engine)
        logger.info(f"Successfully extracted {len(df)} rows.")
        return df
    except Exception as e:
        logger.error(f"Failed to extract data: {e}")
        raise

def transform_data(df):
    """TRANSFORM: Clean, rename, and calculate new fields."""
    logger.info("Starting data transformation...")
    initial_count = len(df)

    # 1. Rename simple mappings
    df = df.rename(columns={
        'last_name': 'nom',
        'first_name': 'prenom',
        'family': 'nums',
        'surname': 'bucque',
        'password': 'password_hash',
        'avatar': 'image'
    })

    df["email"] = df["email"].str.lower() # Normalize email to lowercase
    df["username"] = df["username"].str.lower() # Normalize username to lowercase

    # 2. Logic Transformations
    # is_active (Source) -> is_asleep (Target) : Invert Logic
    df['is_asleep'] = ~df['is_active']

    # 3. Handle Text Transformations and Enum Validation
    valid_tbks = ['ME', 'CL', 'CH', 'KA', 'PA', 'BO', 'LI', 'AN']
    # Ensure tabagnss is string or None, avoid float/NaN
    df['tabagnss'] = df['campus'].astype(str).str.upper().replace('NAN', None).replace('NONE', None)

    # Replace invalid campuses with None to avoid Enum violation
    invalid_campus_count = df.loc[~df['tabagnss'].isin(valid_tbks)].shape[0]
    if invalid_campus_count > 0:
        logger.warning(f"Found {invalid_campus_count} rows with invalid campus codes. Setting them to None.")
        df.loc[~df['tabagnss'].isin(valid_tbks), 'tabagnss'] = None

    # Handle Empty Strings for Unique Columns (phone, email, username)
    # Postgres treats empty strings as unique values, so duplicates fail. Convert to None.
    cols_to_clean = ['image', 'username', 'email']
    for col in cols_to_clean:
        if col in df.columns:
            # Replace empty strings and potential whitespace only strings with None
            df[col] = df[col].astype(str).str.strip().replace('', None).replace('None', None).replace('nan', None)

    # remove user with admin username
    df = df[df['username'] != 'admin']

    # Ensure username is not None (required field)
    # Fallback to email prefix or nom+prenom or a UUID
    missing_username = df['username'].isna()
    if missing_username.any():
        logger.warning(f"Found {missing_username.sum()} rows with missing username. Generating defaults.")
        # Setting username to nom.prenom if missing
        df.loc[missing_username, 'username'] = df.loc[missing_username, 'nom'] + "." + df.loc[missing_username, 'prenom']


    # 4. Handle Numeric/Logic Transformations
    # Convert balance to cents safely
    df['balance'] = (df['balance'].astype(float) * 100).astype(int)
    
    df = df.dropna(subset=['year'])
    # Calculate Gadz Proms Year (e.g. 2023 -> 223)
    df['proms_year'] = df['year'] - 1800
    
    # Calculate promss (handle NaN if tabagnss is None)
    df['promss'] = df.apply(
        lambda row: f"{row['tabagnss']}{int(row['proms_year'])}" if row['tabagnss'] else None, 
        axis=1
    )

    # Filter out rows where promss is None (Required Field)
    invalid_promss = df[df['promss'].isna()]
    if not invalid_promss.empty:
        logger.warning(f"Dropping {len(invalid_promss)} rows with invalid 'promss' (missing tabagnss or year).")
        df = df.dropna(subset=['promss'])

    # 5. Deduplicate (Keep first occurrence)
    len_before_dedup = len(df)
    df = df.drop_duplicates(subset=['email'])
    df = df.drop_duplicates(subset=['username'])
    duplicates_removed = len_before_dedup - len(df)
    if duplicates_removed > 0:
        logger.info(f"Removed {duplicates_removed} duplicate rows.")

    # 6. Filter: Select ONLY columns destined for the new DB
    target_columns = [
        'nom', 'prenom', 'is_asleep', 'nums', 'bucque', 
        'tabagnss', 'balance', 'promss', 'password_hash', 'email',
        'username', 'image'
    ]
    
    final_df = df[target_columns].copy()
    logger.info(f"Transformation complete. {len(final_df)} rows ready for loading (from {initial_count} initial).")
    return final_df

def load_data(df, engine):
    """LOAD: Insert data into the target database."""
    
    if CLEAN_TARGET:
        logger.warning("CLEAN_TARGET is True. Truncating 'users' table...")
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("TRUNCATE TABLE users CASCADE;"))
            conn.commit()
            logger.info("Target table truncated.")

    logger.info(f"Starting load of {len(df)} records into target database...")
    try:
        # Using 'append' - verify if user wants 'replace' later
        df.to_sql('users', engine, if_exists='append', index=False)
        logger.info("✅ Migration success! Data loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to load data: {e}")
        raise

def main():
    logger.info("--- STARTING MIGRATION SCRIPT ---")
    try:
        # Create Engines
        logger.info("Connecting to databases...")
        staging_engine = create_engine(STAGING_URI, connect_args={'client_encoding': 'utf8'})
        target_engine = create_engine(TARGET_URI)

        # Execute ETL Pipeline
        df_raw = get_data(staging_engine)
        df_clean = transform_data(df_raw)
        load_data(df_clean, target_engine)

    except Exception:
        logger.critical("MIGRATION FAILED due to unhandled exception.", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("--- MIGRATION SCRIPT END ---")

if __name__ == "__main__":
    main()
