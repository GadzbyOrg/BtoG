import pandas as pd
from sqlalchemy import create_engine
import sys
import logging
import os

# --- CONFIGURATION ---
STAGING_URI = "postgresql://postgres:password@localhost:5434/old_staging_db"
TARGET_URI  = "postgresql://postgres:password@localhost:5432/gadzby"
CLEAN_TARGET = False  # Set to True to truncate target table before loading
REJECT_LOG_FILE = "migration_rejects.csv"

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def log_rejects(df_rejected, reason):
    """Appends rejected rows to a CSV file with the rejection reason."""
    if df_rejected.empty:
        return
    
    # Create a copy to avoid SettingWithCopyWarning
    df_log = df_rejected.copy()
    df_log['reject_reason'] = reason
    
    # Write header only if the file doesn't exist yet
    write_header = not os.path.exists(REJECT_LOG_FILE)
    df_log.to_csv(REJECT_LOG_FILE, mode='a', index=False, header=write_header)



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

    # 1. Renommage des colonnes
    df = df.rename(columns={
        'last_name': 'nom',
        'first_name': 'prenom',
        'family': 'nums',
        'surname': 'bucque',
        'password': 'password_hash',
        'avatar': 'image'
    })

    # Normalisation basique
    df["email"] = df["email"].str.lower()
    df["username"] = df["username"].str.lower()
    df['is_asleep'] = ~df['is_active']

# 2. Validation du Campus
    valid_tbks = ['ME', 'CL', 'CH', 'KA', 'PA', 'BO', 'LI', 'AN']
    df['tabagnss'] = df['campus'].astype(str).str.upper().str.strip()

    invalid_campus_mask = ~df['tabagnss'].isin(valid_tbks)
    if invalid_campus_mask.any():

        tbk_pattern = r"(" + "|".join(valid_tbks) + r")"
        extracted_tbks = df.loc[invalid_campus_mask, 'username'].astype(str).str.upper().str.extract(tbk_pattern, expand=False)
        df.loc[invalid_campus_mask, 'tabagnss'] = extracted_tbks
        
        invalid_campus_mask = ~df['tabagnss'].isin(valid_tbks)

        if invalid_campus_mask.any():    
            logger.warning(f"Rejecting {invalid_campus_mask.sum()} rows with invalid campus.")
            log_rejects(df[invalid_campus_mask], "Invalid Campus")
            df = df[~invalid_campus_mask].copy()

    # 3. Nettoyage propre des chaînes vides
    cols_to_clean = ['image', 'username', 'email', 'nom', 'prenom']
    for col in cols_to_clean:
        if col in df.columns:
            df[col] = df[col].replace(r'^\s*$', None, regex=True)

    # L'email est obligatoire
    missing_email_mask = df['email'].isna()
    if missing_email_mask.any():
        logger.warning(f"Rejecting {missing_email_mask.sum()} rows without email.")
        log_rejects(df[missing_email_mask], "Missing Email")
        df = df[~missing_email_mask].copy()

    # Suppression de l'admin
    admin_mask = df['username'] == 'admin'
    if admin_mask.any():
        log_rejects(df[admin_mask], "Admin Account Filtered")
        df = df[~admin_mask].copy()

    # 4. Sécurisation des Usernames
    missing_username = df['username'].isna()
    if missing_username.any():
        logger.warning(f"Génération de {missing_username.sum()} usernames manquants.")
        df.loc[missing_username, 'username'] = df.loc[missing_username].apply(
            lambda row: f"{row['nom']}.{row['prenom']}".lower() 
            if pd.notna(row['nom']) and pd.notna(row['prenom']) 
            else str(row['email']).split('@')[0], 
            axis=1
        )

    # 5. Transformations numériques et logiques
    # Remplacer les soldes vides par 0 avant de convertir en centimes
    df['balance'] = (df['balance'].fillna(0).astype(float) * 100).astype(int)
    
    # Sécuriser l'année avant de calculer les proms
    df = df.dropna(subset=['year'])
    df['proms_year'] = df['year'] - 1800
    
    # Génération de la promss (le tabagnss est garanti valide ici)
    df['promss'] = df.apply(
        lambda row: f"{row['tabagnss']}{int(row['proms_year'])}", 
        axis=1
    )

    # 6. Dédoublonnage intelligent
    df = df.sort_values(by=['is_asleep', 'balance'], ascending=[True, False])
    
    # Identify duplicates before dropping them
    dup_email_mask = df.duplicated(subset=['email'], keep='first')
    if dup_email_mask.any():
        logger.info(f"Rejecting {dup_email_mask.sum()} duplicate emails.")
        log_rejects(df[dup_email_mask], "Duplicate Email")
    df = df[~dup_email_mask].copy()

    dup_user_mask = df.duplicated(subset=['username'], keep='first')
    if dup_user_mask.any():
        logger.info(f"Rejecting {dup_user_mask.sum()} duplicate usernames.")
        log_rejects(df[dup_user_mask], "Duplicate Username")
    df = df[~dup_user_mask].copy()

    # 7. Sélection des colonnes cibles
    target_columns = [
        'nom', 'prenom', 'is_asleep', 'nums', 'bucque', 
        'tabagnss', 'balance', 'promss', 'password_hash', 'email',
        'username', 'image'
    ]
    
    final_df = df[target_columns].copy()
    logger.info(f"Transformation complète. {len(final_df)} lignes prêtes (depuis {initial_count} initiales).")
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