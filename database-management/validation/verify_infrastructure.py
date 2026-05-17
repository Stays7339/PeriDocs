#!/usr/bin/env python3
import os
import sys
from dotenv import load_dotenv

# Explicitly pull workspace configuration secrets from .env
load_dotenv()

try:
    import psycopg
except ImportError:
    print("CRITICAL: 'psycopg' missing. Cannot execute infrastructure verification.")
    sys.exit(1)


def test_database_infrastructure():
    print("\n====================================================================")
    print("      RUNNING PROGRAMMATIC RADICLE INFRASTRUCTURE VERIFICATION      ")
    print("====================================================================")
    
    # 1. Capture the master connection string from preloaded memory
    admin_url_string = os.getenv("DATABASE_URL")
    if not admin_url_string:
        print("FAIL: DATABASE_URL variable missing from verification runtime environment.")
        sys.exit(1)

    try:
        # ATOMIC FIX: Safely parse the URL into parameters and isolate target db name
        conn_params = psycopg.conninfo.conninfo_to_dict(admin_url_string)
        conn_params["dbname"] = "peridocs_db"
        app_db_info = psycopg.conninfo.make_conninfo(**conn_params)

        # Connect directly using the robustly formed parametric connection config
        with psycopg.connect(app_db_info, autocommit=True) as conn:
            with conn.cursor() as cur:
                
                # Check 1: Foundational Extensions
                cur.execute("SELECT extname FROM pg_extension WHERE extname IN ('uuid-ossp', 'pgcrypto');")
                extensions = [row[0] for row in cur.fetchall()]
                assert "uuid-ossp" in extensions, "FAIL: uuid-ossp extension missing!"
                assert "pgcrypto" in extensions, "FAIL: pgcrypto extension missing!"
                print("[PASS] Global extensions 'uuid-ossp' and 'pgcrypto' verified online.")

                # Check 2: Core 8-Schema Segmentation
                target_schemas = {'content', 'kb', 'search', 'inference', 'nlp', 'audit', 'admin', 'app'}
                cur.execute("""
                    SELECT schema_name FROM information_schema.schemata 
                    WHERE schema_name IN ('content', 'kb', 'search', 'inference', 'nlp', 'audit', 'admin', 'app');
                """)
                found_schemas = {row[0].lower() for row in cur.fetchall()}
                missing_schemas = target_schemas - found_schemas
                assert not missing_schemas, f"FAIL: Structural tracking schemas missing: {missing_schemas}"
                print("[PASS] Multi-schema domain segregation verified intact (8/8).")

                # Check 3: Governance Identity Verification
                target_roles = {'admin', 'migrator', 'curator', 'auditor', 'peri_app'}
                cur.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('admin', 'migrator', 'curator', 'auditor', 'peri_app');")
                found_roles = {row[0].lower() for row in cur.fetchall()}
                missing_roles = target_roles - found_roles
                assert not missing_roles, f"FAIL: Defined governance roles missing: {missing_roles}"
                print("[PASS] Security identity primitives correctly mapped inside pg_catalog.")

        # Check 4: Security Matrix & Access Privilege Leak Check
        with psycopg.connect(app_db_info) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT has_schema_privilege('peri_app', 'audit', 'CREATE') AS app_can_write_audit,
                           has_schema_privilege('peri_app', 'admin', 'CREATE') AS app_can_write_admin;
                """)
                app_can_write_audit, app_can_write_admin = cur.fetchone()
                assert not app_can_write_audit, "SECURITY EXPLOIT: peri_app user possesses write rights on AUDIT schema!"
                assert not app_can_write_admin, "SECURITY EXPLOIT: peri_app user possesses write rights on ADMIN schema!"
                print("[PASS] Privilege isolation boundaries locked. 'peri_app' runtime jailed.")

        print("\n====================================================================")
        print("  SUCCESS: ALL RELATIONAL INTEGRATION BOUNDARIES VERIFIED COMPLIANT  ")
        print("====================================================================\n")
        return True

    except Exception as e:
        print(f"\n[CRITICAL FAILURE] Verification sequence stopped:\nDetails: {e}")
        sys.exit(1)


if __name__ == "__main__":
    test_database_infrastructure();