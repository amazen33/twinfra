-- Apply as the local CNPG database administrator in vcloud after Module 4a's
-- lifecycle bootstrap. This database-admin migration requires no OS-root Pod.
BEGIN;
SET LOCAL search_path = pg_catalog;
DO $guard$
BEGIN
  IF current_database() <> 'vcloud' OR current_setting('is_superuser') <> 'on' THEN
    RAISE EXCEPTION 'Requires the CNPG-local administrator in vcloud';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_extension WHERE extname='vector' AND extversion='0.8.2') THEN
    RAISE EXCEPTION 'Requires the existing pgvector 0.8.2 extension';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='vcloud_app') OR
     NOT EXISTS (SELECT FROM pg_roles WHERE rolname='vcloud_db_readonly') OR
     to_regprocedure('vcloud_secret_lifecycle.create_login(text,text,timestamp with time zone)') IS NULL THEN
    RAISE EXCEPTION 'Requires CNPG and Module 4a lifecycle bootstrap';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='vcloud_rag_writer') THEN
    CREATE ROLE vcloud_rag_writer NOLOGIN;
  END IF;
  IF EXISTS (SELECT FROM pg_auth_members m JOIN pg_roles r ON m.member=r.oid WHERE r.rolname='vcloud_rag_writer') THEN
    RAISE EXCEPTION 'Writer group must not inherit another role';
  END IF;
  IF EXISTS (SELECT FROM pg_tables WHERE schemaname='public' AND tablename='vcloud_rag_documents' AND tableowner<>'vcloud_app') THEN
    RAISE EXCEPTION 'Refusing an untrusted existing collection';
  END IF;
END;
$guard$;
ALTER ROLE vcloud_rag_writer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE TABLE IF NOT EXISTS public.vcloud_rag_documents (
  langchain_id uuid PRIMARY KEY,
  content text NOT NULL,
  embedding public.vector(384) NOT NULL,
  langchain_metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
ALTER TABLE public.vcloud_rag_documents OWNER TO vcloud_app;
DO $shape$
BEGIN
  IF (SELECT count(*) FROM pg_attribute WHERE attrelid='public.vcloud_rag_documents'::regclass AND attnum>0 AND NOT attisdropped)<>4 OR
     NOT EXISTS (SELECT FROM pg_attribute WHERE attrelid='public.vcloud_rag_documents'::regclass AND attname='embedding' AND atttypid='public.vector'::regtype AND atttypmod=384 AND attnotnull) OR
     NOT EXISTS (SELECT FROM pg_attribute WHERE attrelid='public.vcloud_rag_documents'::regclass AND attname='content' AND atttypid='text'::regtype AND attnotnull) OR
     NOT EXISTS (SELECT FROM pg_attribute WHERE attrelid='public.vcloud_rag_documents'::regclass AND attname='langchain_metadata' AND atttypid='jsonb'::regtype AND attnotnull) OR
     NOT EXISTS (SELECT FROM pg_attribute WHERE attrelid='public.vcloud_rag_documents'::regclass AND attname='langchain_id' AND atttypid='uuid'::regtype AND attnotnull) OR
     NOT EXISTS (SELECT FROM pg_constraint c JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attname='langchain_id'
                 WHERE c.conrelid='public.vcloud_rag_documents'::regclass AND c.contype='p' AND c.conkey=ARRAY[a.attnum]) THEN
    RAISE EXCEPTION 'Existing collection schema differs from the reviewed 384-dimensional store';
  END IF;
END;
$shape$;
REVOKE ALL ON public.vcloud_rag_documents FROM PUBLIC;
GRANT SELECT ON public.vcloud_rag_documents TO vcloud_db_readonly;
GRANT USAGE ON SCHEMA public TO vcloud_rag_writer;
GRANT CONNECT ON DATABASE vcloud TO vcloud_rag_writer;
GRANT SELECT, INSERT, UPDATE ON public.vcloud_rag_documents TO vcloud_rag_writer;
CREATE INDEX IF NOT EXISTS vcloud_rag_documents_cosine_hnsw
  ON public.vcloud_rag_documents USING hnsw (embedding public.vector_cosine_ops);

-- Reuse the audited role-name/SCRAM/expiry guards and issued-role registry.
-- Only this fixed group can be added by the extra writer creation function.
CREATE OR REPLACE FUNCTION vcloud_secret_lifecycle.create_rag_writer(
  p_name text, p_scram text, p_expiration timestamptz
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $writer$
BEGIN
  PERFORM vcloud_secret_lifecycle.create_login(p_name,p_scram,p_expiration);
  EXECUTE format('GRANT vcloud_rag_writer TO %I WITH INHERIT TRUE, SET FALSE',p_name);
END;
$writer$;
ALTER FUNCTION vcloud_secret_lifecycle.create_rag_writer(text,text,timestamptz) OWNER TO postgres;
REVOKE ALL ON FUNCTION vcloud_secret_lifecycle.create_rag_writer(text,text,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION vcloud_secret_lifecycle.create_rag_writer(text,text,timestamptz) TO openbao_manager;
COMMIT;
