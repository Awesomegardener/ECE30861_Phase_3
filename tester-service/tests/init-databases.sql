-- ONLY for a brand-new disposable local Docker volume, never Cloud SQL.
-- Public sample passwords; production credentials must come from Secret Manager.
CREATE ROLE cra_grading_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
    PASSWORD 'local_grading_only';
CREATE ROLE cra_harness LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
    PASSWORD 'local_report_only';
CREATE DATABASE cra_grading;
CREATE DATABASE cra_autograder;
REVOKE ALL ON DATABASE cra_grading FROM PUBLIC;
REVOKE ALL ON DATABASE cra_autograder FROM PUBLIC;
GRANT CONNECT ON DATABASE cra_grading TO cra_grading_app;
GRANT CONNECT, CREATE ON DATABASE cra_autograder TO cra_harness;
\connect cra_grading
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO cra_grading_app;
\connect cra_autograder
REVOKE ALL ON SCHEMA public FROM PUBLIC;
