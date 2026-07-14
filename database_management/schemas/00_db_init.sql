-- ====================================================================
-- PeriDocs RADICLE v0 - Relational Cluster Initialization
-- Save-status: 2026-06-14T17:08-04:00
-- ====================================================================

-- Note: This script must be executed outside a transaction block.
-- It initializes the physical catalog storage engine if absent.

CREATE DATABASE peridocs_db 
    WITH 
    ENCODING = 'UTF8' 
    LC_COLLATE = 'en_US.UTF-8' 
    LC_CTYPE = 'en_US.UTF-8';

