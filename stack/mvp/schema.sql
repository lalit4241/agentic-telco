-- AgenticTelco MVP · L3 Data: one Postgres schema for the MVP journey (operational store, not a lakehouse).
create schema if not exists mvp;
-- conversation (L1/L2)
create table if not exists mvp.conversation (id text primary key, trace_id text, contact_id text, case_name text, started_at timestamptz default now(), state jsonb default '{}');
create table if not exists mvp.message (seq bigserial primary key, conversation_id text, at timestamptz default clock_timestamp(), role text, content text, meta jsonb);
-- identity cross-reference (deterministic, maintained, each link with its source)
create table if not exists mvp.identity_xref (id bigserial primary key, subject text, system text, external_id text, source text, verified boolean default true,
  unique (subject, system));
-- TMF921-shaped Intent + IntentReport (L3 is their system of record)
create table if not exists mvp.intent (id text primary key, conversation_id text, trace_id text, lifecycle_status text, body jsonb, created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists mvp.intent_report (id text primary key, intent_id text, state text, body jsonb, created_at timestamptz default clock_timestamp());
-- consent, decisions
create table if not exists mvp.consent (id bigserial primary key, conversation_id text, contact_id text, text text, at timestamptz default clock_timestamp());
create table if not exists mvp.decision (id bigserial primary key, trace_id text, mode text, policy_version text, input jsonb, result jsonb, at timestamptz default clock_timestamp());
-- order milestones and jeopardy history (the Salesforce order keeps state only)
create table if not exists mvp.milestone (id bigserial primary key, order_ext text, name text, body jsonb, at timestamptz default clock_timestamp());
create table if not exists mvp.jeopardy (id bigserial primary key, order_ext text, body jsonb, at timestamptz default clock_timestamp());
-- workflow idempotency: business key + step → result
create table if not exists mvp.step_result (business_key text, step text, result jsonb, at timestamptz default clock_timestamp(), primary key (business_key, step));
-- legacy stand-in state (mocked systems; the scenario knobs are labelled on screen)
create table if not exists mvp.standin (name text primary key, value jsonb);
-- audit log → L8 timeline (OpenTelemetry-shaped: trace / span / parent, start / end, attributes)
create table if not exists mvp.audit (seq bigserial primary key, trace_id text, span_id text, parent_span_id text, conversation_id text,
  layer text, component text, step text, runtime text, api text, method text, path text, status int,
  start_ts timestamptz, end_ts timestamptz, duration_ms numeric, attributes jsonb, request jsonb, response jsonb);
create index if not exists audit_trace on mvp.audit(trace_id);
