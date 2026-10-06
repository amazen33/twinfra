-- Run once/reconcile as the CNPG-local postgres database administrator in database vcloud.
-- This is SQL superuser setup, not OS-root execution; remote superuser login stays disabled.
-- No password is embedded. Set openbao_manager's initial SCRAM password through a secure
-- interactive psql \password prompt, then register it and rotate it through OpenBao.
BEGIN;
SET LOCAL search_path = pg_catalog;
DO $guard$
BEGIN
  IF current_database() <> 'vcloud' OR current_setting('is_superuser') <> 'on' THEN
    RAISE EXCEPTION 'Requires the local PostgreSQL administrator in database vcloud';
  END IF;
  IF EXISTS (SELECT FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner
             WHERE n.nspname='vcloud_secret_lifecycle' AND r.rolname<>'postgres') THEN
    RAISE EXCEPTION 'Refusing an existing untrusted lifecycle schema';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'openbao_manager') THEN
    CREATE ROLE openbao_manager LOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vcloud_db_readonly') THEN
    CREATE ROLE vcloud_db_readonly NOLOGIN;
  END IF;
  IF EXISTS (SELECT FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member
             WHERE r.rolname IN ('openbao_manager','vcloud_db_readonly')) THEN
    RAISE EXCEPTION 'Lifecycle identities must not inherit or SET other roles';
  END IF;
END;
$guard$;
ALTER ROLE openbao_manager NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
ALTER ROLE vcloud_db_readonly NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT CONNECT ON DATABASE vcloud TO openbao_manager, vcloud_db_readonly;
GRANT USAGE ON SCHEMA public TO vcloud_db_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO vcloud_db_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE vcloud_app IN SCHEMA public GRANT SELECT ON TABLES TO vcloud_db_readonly;

CREATE SCHEMA IF NOT EXISTS vcloud_secret_lifecycle AUTHORIZATION postgres;
ALTER SCHEMA vcloud_secret_lifecycle OWNER TO postgres;
REVOKE ALL ON SCHEMA vcloud_secret_lifecycle FROM PUBLIC;
CREATE TABLE IF NOT EXISTS vcloud_secret_lifecycle.issued_roles (
  role_name name PRIMARY KEY,
  issued_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE vcloud_secret_lifecycle.issued_roles OWNER TO postgres;
REVOKE ALL ON TABLE vcloud_secret_lifecycle.issued_roles FROM PUBLIC, openbao_manager;

CREATE OR REPLACE FUNCTION vcloud_secret_lifecycle.create_login(
  p_name text, p_scram text, p_expiration timestamptz
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $create$
BEGIN
  IF p_name IS NULL OR p_name !~ '^vcloud_(dyn|test)_[A-Za-z0-9]{20}$'
     OR p_scram IS NULL OR p_scram NOT LIKE 'SCRAM-SHA-256$%'
     OR length(p_scram) > 256 OR p_expiration IS NULL
     OR p_expiration <= clock_timestamp()
     OR p_expiration > clock_timestamp() + interval '1 hour 30 seconds' THEN
    RAISE EXCEPTION 'Invalid managed-role request';
  END IF;
  -- Every identifier/value is quoted by PostgreSQL, not concatenated as SQL syntax.
  EXECUTE format('CREATE ROLE %I LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 10 PASSWORD %L VALID UNTIL %L', p_name, p_scram, p_expiration);
  EXECUTE format('GRANT vcloud_db_readonly TO %I WITH INHERIT TRUE, SET FALSE', p_name);
  INSERT INTO vcloud_secret_lifecycle.issued_roles(role_name) VALUES (p_name);
END;
$create$;

CREATE OR REPLACE FUNCTION vcloud_secret_lifecycle.renew_login(
  p_name text, p_expiration timestamptz
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $renew$
BEGIN
  IF p_name IS NULL OR NOT EXISTS (SELECT FROM vcloud_secret_lifecycle.issued_roles WHERE role_name = p_name)
     OR p_expiration IS NULL OR p_expiration <= clock_timestamp()
     OR p_expiration > clock_timestamp() + interval '1 hour 30 seconds' THEN
    RAISE EXCEPTION 'Invalid managed-role renewal';
  END IF;
  EXECUTE format('ALTER ROLE %I VALID UNTIL %L', p_name, p_expiration);
END;
$renew$;

CREATE OR REPLACE FUNCTION vcloud_secret_lifecycle.revoke_login(p_name text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $revoke$
BEGIN
  IF p_name IS NULL OR p_name !~ '^vcloud_(dyn|test)_[A-Za-z0-9]{20}$' THEN
    RAISE EXCEPTION 'Invalid managed-role revocation';
  END IF;
  IF NOT EXISTS (SELECT FROM vcloud_secret_lifecycle.issued_roles WHERE role_name = p_name) THEN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = p_name) THEN
      RAISE EXCEPTION 'Refusing to revoke an unregistered role';
    END IF;
    RETURN; -- Idempotent rollback/revocation after an already-completed cleanup.
  END IF;
  EXECUTE format('ALTER ROLE %I NOLOGIN PASSWORD NULL', p_name);
  -- Only sessions of this registered dynamic role are terminated; the manager has
  -- no general pg_signal_backend or CREATEROLE privilege.
  PERFORM pg_terminate_backend(pid) FROM pg_stat_activity
    WHERE usename = p_name AND pid <> pg_backend_pid();
  EXECUTE format('REVOKE vcloud_db_readonly FROM %I', p_name);
  EXECUTE format('DROP ROLE %I', p_name);
  DELETE FROM vcloud_secret_lifecycle.issued_roles WHERE role_name = p_name;
END;
$revoke$;
ALTER FUNCTION vcloud_secret_lifecycle.create_login(text,text,timestamptz) OWNER TO postgres;
ALTER FUNCTION vcloud_secret_lifecycle.renew_login(text,timestamptz) OWNER TO postgres;
ALTER FUNCTION vcloud_secret_lifecycle.revoke_login(text) OWNER TO postgres;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vcloud_secret_lifecycle FROM PUBLIC;
GRANT USAGE ON SCHEMA vcloud_secret_lifecycle TO openbao_manager;
GRANT EXECUTE ON FUNCTION vcloud_secret_lifecycle.create_login(text,text,timestamptz),
  vcloud_secret_lifecycle.renew_login(text,timestamptz),
  vcloud_secret_lifecycle.revoke_login(text) TO openbao_manager;
COMMIT;
