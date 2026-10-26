# 06 · Tech stack and licences

**Method.** Licence types were read from each project's LICENSE file on its official GitHub repository (default branch) on 26 Oct 2026, or from the vendor's licence page. This is a technical summary, **not legal advice**. Licences can change between releases, so re-check before any public or commercial release. RECOMMENDED.

## 1. Selected stack
| Layer | Component | Role | Licence (CONFIRMED) | Source | Notes |
|---|---|---|---|---|---|
| L1 | React | Intent UI | MIT | [facebook/react](https://github.com/facebook/react) | |
| L1 | Strawberry GraphQL | Optional read-only GraphQL BFF (ADR-008) | MIT | [strawberry-graphql/strawberry](https://github.com/strawberry-graphql/strawberry) | Default choice |
| L1 | Apollo Server | Alternative GraphQL server | MIT | [apollographql/apollo-server](https://github.com/apollographql/apollo-server) | Use Apollo Server only, not Apollo Router (see §3) |
| L1 | bpmn-js | Live BPMN diagram (if used) | MIT plus watermark condition | [bpmn-io/bpmn-js](https://github.com/bpmn-io/bpmn-js) | Licence requires the bpmn.io watermark to stay visible |
| L2 | LangGraph | Agent orchestration | MIT | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | |
| L2 | A2A protocol and a2a-python SDK | Agent-to-agent | Apache-2.0 | [a2aproject/A2A](https://github.com/a2aproject/A2A), [a2aproject/a2a-python](https://github.com/a2aproject/a2a-python) | |
| L2 | MCP Python SDK | Agent tools | MIT | [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) | MCP spec repo: code moving from MIT to Apache-2.0, docs CC-BY-4.0 ([modelcontextprotocol/modelcontextprotocol](https://github.com/modelcontextprotocol/modelcontextprotocol)) |
| L3 | PostgreSQL | Context store, compensation log, Operaton DB | PostgreSQL Licence (OSI-approved, permissive) | [postgresql.org/about/licence](https://www.postgresql.org/about/licence/) | |
| L3 | pgvector | Embeddings | PostgreSQL Licence | [pgvector/pgvector](https://github.com/pgvector/pgvector) | |
| L3 | Apache Kafka | TMF688-style event bus | Apache-2.0 | [apache/kafka](https://github.com/apache/kafka) | |
| L4 | Open Policy Agent | Policy decisions | Apache-2.0 | [open-policy-agent/opa](https://github.com/open-policy-agent/opa) | |
| L5 | Operaton | BPMN engine | Apache-2.0 | [operaton/operaton](https://github.com/operaton/operaton), [FAQ](https://operaton.org/faq/) | No commercial tier; ~6-month support per version, no LTS |
| L5 | operaton-mcp | Optional MCP access to Operaton | Apache-2.0 | [operaton/operaton-mcp](https://github.com/operaton/operaton-mcp) | Restrict to start/read (ADR-003) |
| L6 | FastAPI | SoR stand-in, adapters | MIT | [fastapi/fastapi](https://github.com/fastapi/fastapi) | |
| L7 | Docker Compose | One-command stack | Apache-2.0 | [docker/compose](https://github.com/docker/compose) | Use Docker Engine on Linux. Docker Desktop has separate commercial subscription terms (INFERRED; check if used) |
| L7 | k3s | Optional Kubernetes | Apache-2.0 | [k3s-io/k3s](https://github.com/k3s-io/k3s) | |
| L7 | LiteLLM | Inference Gateway (ADR-009) | MIT, except `enterprise/` directory under a separate commercial licence | [BerriAI/litellm](https://github.com/BerriAI/litellm) | Use MIT core only; check each feature's location |
| L7 | vLLM | Local model serving | Apache-2.0 | [vllm-project/vllm](https://github.com/vllm-project/vllm) | Model **weights** have their own licences; check per model |
| L7 | Ollama | Local model serving (laptop) | MIT | [ollama/ollama](https://github.com/ollama/ollama) | As above |
| L8 | OpenTelemetry (collector, Python SDK) | Traces, metrics | Apache-2.0 | [open-telemetry/opentelemetry-collector](https://github.com/open-telemetry/opentelemetry-collector), [open-telemetry/opentelemetry-python](https://github.com/open-telemetry/opentelemetry-python) | |
| L8 | Jaeger | Trace UI | Apache-2.0 | [jaegertracing/jaeger](https://github.com/jaegertracing/jaeger) | |
| L8 | Prometheus | Metrics | Apache-2.0 | [prometheus/prometheus](https://github.com/prometheus/prometheus) | |
| L8 | Grafana | Dashboards | AGPL-3.0 | [grafana/grafana](https://github.com/grafana/grafana) | OSI open source, copyleft. Fine unmodified; changes served over a network must be shared |
| L8 | Langfuse | Agent traces, evals, cost | MIT, except `ee/` directories | [langfuse/langfuse](https://github.com/langfuse/langfuse) | Use MIT core only |

## 2. Alternatives considered (open source)
| Component | Licence (CONFIRMED) | Source | Why not selected |
|---|---|---|---|
| Temporal | MIT | [temporalio/temporal](https://github.com/temporalio/temporal) | Code-defined workflows, not BPMN. Fallback for L5. Currently in DevBot's L5 code (see ADR-007) |
| Flowable | Apache-2.0 | [flowable/flowable-engine](https://github.com/flowable/flowable-engine) | Viable; Operaton preferred |
| Conductor (conductor-oss) | Apache-2.0 | [conductor-oss/conductor](https://github.com/conductor-oss/conductor) | JSON workflows, not BPMN |
| CrewAI | MIT | [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | LangGraph gives more explicit state control |
| AutoGen | Code MIT, docs CC-BY-4.0 | [microsoft/autogen](https://github.com/microsoft/autogen) | As above |
| Google ADK (Python) | Apache-2.0 | [google/adk-python](https://github.com/google/adk-python) | As above |
| Qdrant | Apache-2.0 | [qdrant/qdrant](https://github.com/qdrant/qdrant) | pgvector avoids a second database |
| Milvus | Apache-2.0 | [milvus-io/milvus](https://github.com/milvus-io/milvus) | As above |
| Cedar | Apache-2.0 | [cedar-policy/cedar](https://github.com/cedar-policy/cedar) | OPA is more widely used for general policy |
| OpenFGA | Apache-2.0 | [openfga/openfga](https://github.com/openfga/openfga) | Relationship authorisation, not business policy |
| Microsoft Presidio | MIT | [microsoft/presidio](https://github.com/microsoft/presidio) | Candidate for PII stripping in the gateway; not yet chosen |

## 3. Rejected on licence
| Component | Licence (CONFIRMED) | Source | Why rejected |
|---|---|---|---|
| Camunda 8 (8.6+) | Camunda License 1.0 (source-available); production use needs a commercial licence | [Camunda licences](https://docs.camunda.io/docs/reference/licenses/), [Camunda blog](https://camunda.com/blog/2024/10/camunda-licensing-what-you-need-to-know/) | Not open source for production |
| Redpanda | Business Source License 1.1 (core) | [redpanda-data/redpanda](https://github.com/redpanda-data/redpanda) | Not OSI open source |
| Restate | Business Source License 1.1 | [restatedev/restate](https://github.com/restatedev/restate) | Not OSI open source |
| Apollo Router | Elastic License 2.0 | [apollographql/router](https://github.com/apollographql/router) | Not OSI open source |

## 4. Salesforce (the only commercial component)
- Salesforce Communications Cloud, used as L6 SoR only, under Salesforce's own commercial terms. A 30-day trial on Salesforce Platform has been created. REPORTED.
- TMF API availability depends on licences: Salesforce lists TMF620 v4 and TMF648 v4 as **managed package only**, while TMF679 v5, TMF622 v5, TMF637 v5 and TMF632 v5 are listed for **Salesforce Platform** ([Salesforce TMF page](https://developer.salesforce.com/docs/industries/communications/guide/TMF_compliance.html), CONFIRMED). Whether the trial org has the managed package or the permission set licences TMF620 needs is UNKNOWN.

## 5. Things to keep checking
- LiteLLM and Langfuse: features in `enterprise/` or `ee/` are not open source. Confirm each feature we use is in the core.
- Grafana AGPL-3.0: do not ship a modified Grafana without publishing the changes.
- bpmn-js watermark must remain visible.
- Open-weight model licences (for example Llama, Mistral, Qwen, Gemma) differ from the serving software. Record the model licence for each model used.
