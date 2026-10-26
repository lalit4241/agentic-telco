# ADR 0001 (dev): LiteLLM MIT core hosted in the L7 runtime, used by the L2 agent mesh

- **Status:** Accepted (demo), 2026-10-26.
- **Context:** Zero Gravity's L2 agents need models, and L7 is the runtime and identity layer. The report gives model access no layer of its own. We must not invent a ninth layer, and customer data may only go to local or sovereign models.
- **Decision:**
  - The **LiteLLM proxy (MIT core only)** runs as a process in the **L7 runtime**. The `litellm-enterprise` package is uninstalled at setup. Version 1.106.2 listens on 127.0.0.1:4000.
  - It sits behind our small **inference gateway** (`stack/inference`, port 8110):
    - It redacts PII and applies a semantic cache.
    - It asks **OPA (L4)** which models a caller may use for a given data class. Customer data → local or sovereign models only, and OPA and the Operaton workers may never call a model.
    - It records each call in the **L8** ledger.
  - **Only the L2 agent mesh** calls it. The UI calls this "hosted in L7 runtime, used by L2 agent mesh – our extension of the Zero Gravity framework (not a ninth layer)".
  - The model is Ollama `qwen2.5:0.5b`, run locally. A deterministic parser cross-checks extraction. The recorded run used **0 stub calls**.
- **Alternatives:** direct SDK calls from each agent (no central policy or budget), or a commercial gateway (licence, data residency). Langfuse, MIT core only, is an optional tracing add-on.
- **Consequences:** model choice is a policy decision in L4, not code in agents. Swapping models is a LiteLLM config change (`stack/inference/litellm.yaml`). The master key lives in `.data/secrets.env`, which is git-ignored and never shipped.
