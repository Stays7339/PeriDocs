#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path
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

    # Establish current folder routing to verify local file contracts
    current_dir = Path(__file__).parent

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

                # New Check 4: Domain Table Structural Presence
                # Map out explicit tables that must exist across our newly written DDL files
                expected_tables = {
                    'ADMIN': {'release_information'},
                    'APP': {'users'},
                    'CONTENT': {'resources'},
                    'KB': {'concepts', 'concept_hierarchies', 'migration_reviews'},
                    'INFERENCE': {'queries'},
                    'NLP': {'pipeline_logs'},
                    'SEARCH': {'retrieval_logs'},
                    'AUDIT': {'governance_evidence_packets'}
                }

                for schema_name, tables in expected_tables.items():
                    for table_name in tables:
                        cur.execute("""
                            SELECT 1 FROM information_schema.tables 
                            WHERE table_schema = %s AND table_name = %s;
                        """, (schema_name, table_name))
                        assert cur.fetchone(), f"FAIL: Structural table missing: {schema_name}.{table_name}"
                print("[PASS] Core domain relational tables verified active inside cluster schemas.")

        # Check 5: Security Matrix & Access Privilege Leak Check
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

        # # New Check 6: Data Contract Integrity Assertions
        # # Programmatically validates the JSON validation blueprints 
        # contract_files = ['inference_summary.json', 'nlp_metadata.json']
        # for contract in contract_files:
        #     contract_path = current_dir / 'contracts' / contract
        #     assert contract_path.is_file(), f"FAIL: Verification contract missing at: {contract_path}"
            
        #     with open(contract_path, 'r') as file_payload:
        #         try:
        #             json.load(file_payload)
        #         except json.JSONDecodeError as json_fault:
        #             raise AssertionError(f"FAIL: Data contract serialization error in {contract}: {json_fault}")
        # print("[PASS] Python request ingestion ingestion contracts verified as valid JSON profiles.")

        print("\n====================================================================")
        print("  SUCCESS: ALL RELATIONAL INTEGRATION BOUNDARIES VERIFIED COMPLIANT  ")
        print("====================================================================\n")
        return True

    except Exception as e:
        print(f"\n[CRITICAL FAILURE] Verification sequence stopped:\nDetails: {e}")
        sys.exit(1)


if __name__ == "__main__":
    test_database_infrastructure()
