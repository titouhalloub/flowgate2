# Model tiers

Flowgate's pipeline runs on top of a language model. There are two
deployments, and the model tier is the only thing that differs between
them. The code, the pipeline, the compliance rules, and the ledger are
identical.

## Production — high-performance models

Production deployments run on paid, high-performance models served
through OpenRouter. Current production default:

    Anthropic Claude Sonnet 4 (via OpenRouter)
    or Google Gemini 2.0 Flash as a lower-latency alternative

These models are:

- **Stable** — no silent model removal, no upstream churn
- **Fast** — typical classification + extraction round trip under 10s
- **Reliable** — no rate-limit 429s on standard load
- **Zero-retention on request** — a signed data-processing addendum is
  available for regulated customers

**Flowgate operates the models.** You do not need to bring your own
API key. There is no per-customer model configuration. The
infrastructure is Flowgate's, and the data handling terms are
negotiated once, not per deployment.

## Demo — free tier

Public demo and development deployments run on OpenRouter's free tier
for cost reasons. Current demo default:

    nvidia/nemotron-3-super-120b-a12b:free

The demo is functionally identical — same code, same pipeline, same
compliance engine — but:

- Extraction may take 30–60s per document instead of 5–10s
- Occasional 503s from the upstream provider trigger a retry, then a
  fallback to the deterministic heuristic extractor
- Free-tier models are not covered by a zero-retention agreement; do
  not submit PII or confidential documents to the demo

The demo exists so you can evaluate the product without asking us for
credentials. Production is where real documents go.

## Enterprise — self-hosted

Customers with data-residency requirements (EU, KSA, UAE) can run the
same pipeline against a self-hosted open-weights model on their own
infrastructure. Supported models:

    Llama 3.3 70B Instruct
    Qwen 2.5 72B Instruct
    Mistral Large

The backend reads the model endpoint from an environment variable, so
no code change is required. This is negotiated as part of the
enterprise plan and deployed on the customer's cloud tenant.

## What this means in practice

| Tier | Who runs the model | Typical latency | Data retention | Customer action |
|---|---|---|---|---|
| Demo | Flowgate, free tier | 30–60s | None guaranteed | None |
| Production | Flowgate, paid | 5–10s | Zero-retention on request | None |
| Enterprise | Customer's tenant | 5–10s | Customer-controlled | Cloud infra |

## How to tell which tier you are on

`GET /config` (public) reports the active backend and whether the
free tier is in use:

    {
      "llm_backend": "openrouter",
      "llm_model": "nvidia/nemotron-3-super-120b-a12b:free",
      "llm_is_free_tier": true
    }

The same information is logged once on server startup. If you see
`free-tier: True` in a production environment, something is
misconfigured and should be reported.

## What is not offered

- **Bring-your-own-key.** We run the models. Customer-operated API
  keys are an enterprise-plan feature, not a self-serve option.
- **Per-request model selection.** The pipeline uses one backend
  consistently. There is no per-endpoint or per-document override.
- **Model choice at the customer level.** Model selection is a
  deployment-time decision, not a user-facing setting.