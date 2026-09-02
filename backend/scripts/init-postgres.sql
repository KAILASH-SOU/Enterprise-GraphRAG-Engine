-- Enable uuid-ossp for primary keys
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- We can create roles or schemas for multi-tenancy if needed.
-- SQLAlchemy will handle table creation and we will use SET LOCAL for RLS.
