#!/usr/bin/env sys executable
# ==========================================
# save-state 2026-06-14T17:02-04:00
# setup.py
# ==========================================
import os
import subprocess
import sys
from dotenv import load_dotenv

load_dotenv()

# Attempt to load native psycopg tool for Python-to-Postgres communication
try:
    import psycopg
except ImportError:
    print("CRITICAL: 'psycopg' library not found. Please run: pip install psycopg[binary]")
    sys.exit(1)


def run_pipeline_script(script_name):
    """Safely runs a sibling python validation/setup script."""
    print(f"\n--> Executing pipeline component: {script_name}")
    try:
        subprocess.run([sys.executable, script_name], check=True)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Initialization stage {script_name} failed (Code: {e.returncode}).")
        sys.exit(1)


def apply_sql_blueprint(cursor, file_path):
    """Reads a pure SQL design artifact and passes it straight to the cluster."""
    print(f"Applying relational blueprint: {file_path}")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            sql_script = f.read()
        cursor.execute(sql_script)
    except Exception as e:
        print(f"DATABASE UPGRADE ERROR in {file_path}:\n{e}")
        raise e


def initialize_peridocs_database():
    """Establishes connections and applies roles, schemas, and structural bounds."""
    print("\n--> Initializing Relational Storage Frame...")

    # --- DYNAMIC TARGET RESOLUTION ---
    DATABASE_MODE = os.getenv("DATABASE_MODE", "OFFLINE_MOCK").upper()

    # 1. Capture administrative cluster configuration string from .env
    if DATABASE_MODE == "PRODUCTION":
        # If explicitly setting PRODUCTION, target the real Hetzner cluster connection string
        admin_url_string = os.getenv("DATABASE_URL")
        print("\n[WARNING] setup.py is targeting the LIVE REMOTE HETZNER PRODUCTION ENVIRONMENT! ⚠️")
    elif DATABASE_MODE == "LOCAL":
        # Default to your safe, local loopback database sandbox string
        admin_url_string = os.getenv("LOCAL_DATABASE_URL")
        print("\n[LOCAL] setup.py is targeting your LOCAL SANDBOX DATABASE environment.")
    else:
        print("\n[OFFLINE_MOCK] bypassing database requirements") 
        return True   

    if not admin_url_string:
        print(f"FAIL: Appropriate database string missing for mode: {DATABASE_MODE}")
        sys.exit(1)

    # Ensure the user has an intentional pause to cancel if they accidentally run production
    if DATABASE_MODE == "PRODUCTION":
        confirm = input("Are you absolutely sure you want to run mutations on production? (type 'yes'): ")
        if confirm.lower() != 'yes':
            print("Aborting production mutation run.")
            sys.exit(0)

    try:
        # STEP 1: Run physical database check on administrative master catalog
        with psycopg.connect(admin_url_string, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname='peridocs_db'")
                exists = cur.fetchone()
                
                if not exists:
                    print("Catalog 'peridocs_db' absent. Physicalizing base cluster storage...")
                    apply_sql_blueprint(cur, "database-management/schemas/00_db_init.sql")
                else:
                    print("Catalog 'peridocs_db' verified online.")

        # STEP 2: The Context Switch (The Robust Parametric Approach)
        # We parse the raw connection URL string into a structured parameter dictionary mapping
        conn_params = psycopg.conninfo.conninfo_to_dict(admin_url_string)
        
        # Explicitly pivot the target database key while preserving user/password values perfectly
        conn_params["dbname"] = "peridocs_db"
        
        # Re-serialize the parameterized map into an isolated connection utility object
        app_db_info = psycopg.conninfo.make_conninfo(**conn_params)

        # STEP 3: The Extension Guarantee Pass
        # We utilize our verified, structured app_db_info connection block
        print("Ensuring foundational crypto and tokenization extensions are present...")
        with psycopg.connect(app_db_info, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
                cur.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
                print("Extensions successfully verified/installed.")

        # STEP 4: Build out Multi-Schema and Least Privilege Role Paradigms
        with psycopg.connect(app_db_info, autocommit=True) as conn:
            with conn.cursor() as cur:
                apply_sql_blueprint(cur, "database-management/schemas/01_roles_init.sql")
                apply_sql_blueprint(cur, "database-management/schemas/02_schemas_init.sql")
                apply_sql_blueprint(cur, "database-management/schemas/03_permissions.sql")
                apply_sql_blueprint(cur, "database-management/schemas/tables/content_tables.sql")
                apply_sql_blueprint(cur, "database-management/schemas/tables/kb_tables.sql")
                apply_sql_blueprint(cur, "database-management/schemas/tables/ledger_tables.sql")
                apply_sql_blueprint(cur, "database-management/schemas/tables/nlp_tables.sql")
                apply_sql_blueprint(cur, "database-management/schemas/tables/app_tables.sql")
                apply_sql_blueprint(cur, "database-management/schemas/tables/search_tables.sql")
                
    except Exception as e:
        print(f"CRITICAL: Structural provisioning halted.\nDetails: {e}")
        sys.exit(1)

def main():
    print("====================================================================")
    print("          PeriDocs RADICLE Initialization & Bootstrapper            ")
    print("====================================================================")

    # Step 1: Ensure machine learning model architecture is provisioned
    run_pipeline_script("setup_roberta.py")

    # Step 2: Provision your relational cluster, 4 roles, and 8 schemas
    initialize_peridocs_database()

    # Step 3: Trigger your external validation runner file cleanly
    # This separates installation code from pipeline verification rules.
    run_pipeline_script(os.path.join("database-management", "validation", "verify_infrastructure.py"))

    print("\n====================================================================")
    print("  Success: Workspace synchronized cleanly. Environmental boundaries live.  ")
    print("====================================================================")


if __name__ == "__main__":
    main()
