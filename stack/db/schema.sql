-- AgenticTelco · Zero Gravity stack — one Postgres (pgvector), one schema per layer/owner.
create extension if not exists vector;
create schema if not exists sor;  -- L6 stand-in for Salesforce Comms Cloud (system of record ONLY)
create schema if not exists oss;  -- mocked Production OSS
create schema if not exists l3;   -- our data products + knowledge (pgvector)
create schema if not exists l4;   -- our context & policy versions / decision log
create schema if not exists l5;   -- our durable saga log
create schema if not exists l8;   -- our trace & audit ledger

-- L6: records + product configuration only. No credit / consent / network rules live here.
create table if not exists sor.party (id text primary key, name text, email text, consent jsonb, created_at timestamptz default now());
create table if not exists sor.customer (id text primary key, party_id text references sor.party(id), name text, status text,
  address jsonb, sf_account_name text, created_at timestamptz default now());
create table if not exists sor.product_offering (id text primary key, name text, description text, price_gbp numeric,
  download_mbps int, required_technology text[], lifecycle_status text default 'Launched', body jsonb);
create table if not exists sor.product_inventory (id text primary key, customer_id text, offering_id text, status text, start_date timestamptz default now());
create table if not exists sor.quote (id text primary key, body jsonb, state text, created_at timestamptz default now());
create table if not exists sor.qualification (id text primary key, body jsonb, created_at timestamptz default now());
create table if not exists sor.product_order (id text primary key, body jsonb, state text, created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists sor.idempotency (key text primary key, method text, path text, status int, response jsonb, created_at timestamptz default now());

-- OSS (mocked)
create table if not exists oss.service_order (id text primary key, body jsonb, state text, created_at timestamptz default now());
create table if not exists oss.trouble_ticket (id text primary key, body jsonb, status text, created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists oss.capacity (exchange text primary key, ports_total int, ports_reserved int, utilisation numeric);
create table if not exists oss.reservation (id text primary key, exchange text, order_ref text, state text, created_at timestamptz default now());
create table if not exists oss.idempotency (key text primary key, status int, response jsonb);
create table if not exists oss.fault_injection (name text primary key, value jsonb);

-- L3 data products
create table if not exists l3.credit_score (customer_id text primary key, score int, bureau text, as_of date);
create table if not exists l3.usage (customer_id text primary key, avg_monthly_gb int, peak_mbps int, devices int, wfh boolean);
create table if not exists l3.knowledge (id text primary key, title text, body text, embedding vector(64));

-- L4 policy versions + decision log
create table if not exists l4.policy_version (version int primary key, data jsonb, author text, reason text,
  changed_at timestamptz default now(), salesforce_calls_during_change int default 0);
create table if not exists l4.decision (id bigserial primary key, run_id text, policy_version int, input jsonb, result jsonb, at timestamptz default now());

-- L5 durable saga log (idempotency key per step, persisted compensations)
create table if not exists l5.saga (workflow_id text primary key, run_id text, engine text, state text, input jsonb, result jsonb,
  created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists l5.saga_step (id bigserial primary key, workflow_id text, step text, idem_key text, status text,
  attempt int, output jsonb, compensation jsonb, worker text, at timestamptz default clock_timestamp());

-- L8 ledger
create table if not exists l8.runs (run_id text primary key, scenario text, title text, customer_id text, utterance text, started_at timestamptz default now(),
  finished_at timestamptz, outcome text, summary jsonb, model_routes jsonb default '[]');
create table if not exists l8.api_calls (seq bigserial primary key, at timestamptz default clock_timestamp(), run_id text, trace_id text,
  caller text, callee text, method text, path text, status int, api text, api_name text, layer text, oda_block text, owner text,
  runtime text, sf_certified boolean, note text, request jsonb, response jsonb, duration_ms numeric, extra jsonb);
create table if not exists l8.events (seq bigserial primary key, at timestamptz default clock_timestamp(), subject text, run_id text, body jsonb);
create index if not exists api_calls_run on l8.api_calls(run_id);

-- Shared inference service (hosted in L7 runtime, used by L2 agent mesh) – our extension of the Zero Gravity framework
create table if not exists l3.semantic_cache (id bigserial primary key, task_class text, model text, scope text, prompt text, embedding vector(64),
  response jsonb, created_at timestamptz default now());
create table if not exists l8.inference (seq bigserial primary key, at timestamptz default clock_timestamp(), run_id text, agent text,
  task_class text, data_class text, routed_model text, served_by text, route text, cache text, pii_redacted int, prompt_tokens int,
  completion_tokens int, cost_gbp numeric, latency_ms numeric, budget jsonb, opa jsonb, fallbacks jsonb, stub boolean, trace_id text);
create index if not exists inference_run on l8.inference(run_id);
