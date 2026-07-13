#!/usr/bin/env sys executable
# ==========================================
# PeriDocs/setup.py
# save-state 2026-07-12T14:49-04:00
# ==========================================
import os
import subprocess
import sys
import psycopg
import re
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


# def sync_blueprints_declaratively(cursor, blueprint_files: list, live_schemas: list):
#     SHADOW_SCHEMA = "blueprint_shadow"
    
#     print("\n[DECLARATIVE SYNC] Generating structural diff from blueprints...")
    
#     # Step 1: Create a clean, isolated shadow schema
#     cursor.execute(f"DROP SCHEMA IF EXISTS {SHADOW_SCHEMA} CASCADE;")
#     cursor.execute(f"CREATE SCHEMA {SHADOW_SCHEMA};")
    
#     # Step 2: Read blueprints, rewrite target schemas to point to the shadow schema, and run them
#     for file_path in blueprint_files:
#         with open(file_path, "r", encoding="utf-8") as f:
#             sql_content = f.read()
        
#         # Rewrite "app.", "content.", "kb." to "blueprint_shadow." so they build in isolation
#         for schema in live_schemas:
#             sql_content = re.sub(rf"\b{schema}\.", f"{SHADOW_SCHEMA}.", sql_content)
            
#         try:
#             cursor.execute(sql_content)
#         except Exception as e:
#             print(f"Shadow compilation failed for {file_path}: {e}")
#             cursor.execute(f"DROP SCHEMA IF EXISTS {SHADOW_SCHEMA} CASCADE;")
#             return

#     # Step 3: Compare structural metadata using PostgreSQL information_schema
#     # Find columns that exist in the blueprints (shadow) but are completely missing in the live DB
#     for schema in live_schemas:
#         diff_query = """
#             SELECT 
#                 s.table_name, 
#                 s.column_name, 
#                 s.data_type, 
#                 s.character_maximum_length,
#                 s.is_nullable
#             FROM information_schema.columns s
#             LEFT JOIN information_schema.columns l 
#               ON l.table_schema = %s 
#              AND l.table_name = s.table_name 
#              AND l.column_name = s.column_name
#             WHERE s.table_schema = %s
#               AND l.column_name IS NULL;
#         """
#         cursor.execute(diff_query, (schema, SHADOW_SCHEMA))
#         missing_columns = cursor.fetchall()
        
#         # Step 4: Dynamically generate and apply ALTER statements for missing columns
#         for row in missing_columns:
#             table, column, data_type, char_len, is_nullable = row
            
#             # Format data type properly if it has a max character length
#             type_str = f"{data_type}({char_len})" if char_len else data_type
#             null_str = "NULL" if is_nullable == "YES" else "NOT NULL DEFAULT ''" # basic fallback safety
            
#             alter_sql = f"ALTER TABLE {schema}.{table} ADD COLUMN {column} {type_str};"
#             print(f"[AUTO-MIGRATE] Structural drift detected! Applying: {alter_sql}")
            
#             try:
#                 cursor.execute(alter_sql)
#             except Exception as e:
#                 print(f"Failed to auto-apply shift to {schema}.{table}: {e}")

#     # Step 5: Clean slate cleanup of the shadow schema
#     cursor.execute(f"DROP SCHEMA IF EXISTS {SHADOW_SCHEMA} CASCADE;")
#     print("[DECLARATIVE SYNC] Synchronization complete. Live data intact.")


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
    elif DATABASE_MODE == "SANDBOX":
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

                # ---------------------------------------------------------
                # NEW: SANDBOX TEARDOWN GUARD FOR TRULY FORKABLE SLATES
                # ---------------------------------------------------------
                if DATABASE_MODE == "SANDBOX":
                    print("\n[CLEAN SLATE] Terminating lingering processes and dropping local sandbox...")
                    # Terminate any zombie server connections blocking a database drop
                    cur.execute("""
                        SELECT pg_terminate_backend(pg_stat_activity.pid)
                        FROM pg_stat_activity
                        WHERE pg_stat_activity.datname = 'peridocs_db'
                          AND pid <> pg_backend_pid();
                    """)
                    cur.execute("DROP DATABASE IF EXISTS peridocs_db;")
                    print("[CLEAN SLATE] Old local database dropped successfully.")
                # ---------------------------------------------------------

                cur.execute("SELECT 1 FROM pg_database WHERE datname='peridocs_db'")
                exists = cur.fetchone()
                
                if not exists:
                    print("Catalog 'peridocs_db' absent. Physicalizing base cluster storage...")
                    apply_sql_blueprint(cur, "database_management/schemas/00_db_init.sql")
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
                """
                NOTE: The order is specific here, since PostgresSQL can be 
                finicky with creating and filling interdependent tables if those tables
                don't already exist by the time the line of code runs, 
                so this particular sequential order is pretty importent.
                """

                apply_sql_blueprint(cur, "database_management/schemas/01_roles_init.sql")
                apply_sql_blueprint(cur, "database_management/schemas/02_schemas_init.sql")
                apply_sql_blueprint(cur, "database_management/schemas/03_permissions_init.sql")
                
                # Core operational content layout
                apply_sql_blueprint(cur, "database_management/schemas/tables/content_schema.sql")
                
                # MOVED UP: Provision core app infrastructure, admin tracking, and user tables
                apply_sql_blueprint(cur, "database_management/schemas/tables/app_schema.sql")
                
                # Now that app.accounts and admin.release_information exist, KB can safely build
                apply_sql_blueprint(cur, "database_management/schemas/tables/kb_schema.sql")
                
                # Remaining downstream dependencies
                apply_sql_blueprint(cur, "database_management/schemas/tables/ledger_schema.sql")
                apply_sql_blueprint(cur, "database_management/schemas/tables/centroid_schema.sql")

                # =============== Run the declarative auto-differ to apply column updates automatically ===============
                blueprints = [
                    "database_management/schemas/tables/app_schema.sql",
                    "database_management/schemas/tables/kb_schema.sql",
                    "database_management/schemas/tables/content_schema.sql"
                ]
                live_schemas = ["app", "kb", "content"]
                
                #sync_blueprints_declaratively(cur, blueprints, live_schemas)
                
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
    run_pipeline_script(os.path.join("database_management", "validation", "verify_infrastructure.py"))

    print("\n====================================================================")
    print("  Success: Workspace synchronized cleanly. Environmental boundaries live.  ")
    print("====================================================================")


if __name__ == "__main__":
    main()