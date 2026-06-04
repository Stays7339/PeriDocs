-- ====================================================================
-- PeriDocs RADICLE v0 - Relational Cluster Initialization
-- Created: 2026-05-16T13:40:00-04:00 by MB
-- Updated: 2026-05-16T13:40:00-04:00 by MB
-- ====================================================================

-- Note: This script must be executed outside a transaction block.
-- It initializes the physical catalog storage engine if absent.

SELECT 'Provisioning physical catalog storage container...' AS status;

CREATE DATABASE peridocs_db 
    WITH 
    ENCODING = 'UTF8' 
    LC_COLLATE = 'en_US.UTF-8' 
    LC_CTYPE = 'en_US.UTF-8';

SELECT 'Catalog container initialized successfully.' AS status;
