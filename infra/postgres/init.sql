-- Runs once when the Postgres volume is first created.
-- Extensions used by search and semantic matching (later phases).
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
-- Separate database for the automated test suite.
CREATE DATABASE talentmatch_test OWNER talentmatch;
\connect talentmatch_test
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
