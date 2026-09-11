# Vendor setup

Read from vendor documentation on 2026-09-11. Each section says what the docs
confirm and what still has to be settled by hand. Nothing here has been run.

## Gemma

- Model overview and downloads: [ai.google.dev/gemma/docs/core](https://ai.google.dev/gemma/docs/core)
- QLoRA fine-tuning guide: [huggingface_text_finetune_qlora](https://ai.google.dev/gemma/docs/core/huggingface_text_finetune_qlora)
- Weights: [Hugging Face](https://huggingface.co/google) and [Kaggle](https://www.kaggle.com/models/google/gemma)

The current generation is Gemma 4, published in four architectures.

| Variant | Parameters | Context | Notes |
|---|---|---|---|
| E2B / E4B | 2B / 4B effective | 128K | edge oriented |
| 12B | 12B | 256K | unified, encoder-free multimodal |
| 31B | 31B | 256K | dense |
| 26B A4B | 26B, 4B active per token | 256K | mixture of experts |

Gemma 3, 2 and 1 model cards remain available.

E4B and the 12B are the realistic candidates for a small supported checkpoint.
Pin the exact revision only after the serving test below, not before.

The official guide requires `transformers>=5.10.1` and `peft>=0.19.0`, plus
bitsandbytes, TRL, accelerate and datasets. Its published configuration is nf4
with double quantization, bfloat16 compute where the GPU supports it, LoRA rank
16, alpha 16, dropout 0.05, no bias, task type `CAUSAL_LM`, and `lm_head` plus
`embed_tokens` in `modules_to_save` for special token handling.

Its training arguments are max length 512, per-device batch size 1, three
epochs, learning rate 2e-4, constant scheduler, `adamw_torch_fused`. This
repository's `training/sft.py` currently carries rank 16, learning rate 1e-4
and one epoch. Both sets are candidates. The guide's numbers come from a
different task and are not evidence for this one.

Two figures worth planning around. The guide runs Gemma 1B on a 16 GB T4.
Merging an adapter needs more than 30 GB of CPU memory, so merging belongs on
the instance rather than on a laptop.

The `modules_to_save` entry matters here specifically. The answer format is a
fixed JSON object rather than free prose, so any added special token means the
embedding and head have to train alongside the adapter.

## vLLM and LoRA serving

- LoRA documentation: [docs.vllm.ai/en/latest/features/lora.html](https://docs.vllm.ai/en/latest/features/lora.html)
- Supported models: [docs.vllm.ai/en/latest/models/supported_models](https://docs.vllm.ai/en/latest/models/supported_models/)

Server flags are `--enable-lora`, `--lora-modules`, `--max-loras` and
`--max-lora-rank`. A request selects an adapter by name, several adapters can be
served at once, and adapters can be added or reloaded at runtime.

**There is a specific risk here, and it is the kind that ruins a demo quietly.**

[Issue #39246](https://github.com/vllm-project/vllm/issues/39246), "Add LoRA
support for Gemma4ForConditionalGeneration", is closed with an accompanying pull
request, so Gemma 4 LoRA support has landed for both `Gemma4ForCausalLM` and
`Gemma4ForConditionalGeneration`.

[Issue #41754](https://github.com/vllm-project/vllm/issues/41754) is the one to
worry about. Unsloth-trained Gemma 4 LoRA adapters load without an error and are
then ignored during inference. The report describes it as silent, reproduced on
an RTX 4090 and an A6000 Pro with the 31B, with no identified root cause and no
confirmed workaround. Adapter loading is reported to work normally for Gemma 3,
Mistral and Qwen, and the same adapters apply correctly through
[Unsloth](https://github.com/unslothai/unsloth)'s own `FastModel`. The problem
is specific to Gemma 4 under vLLM.

The consequence is direct. A silently ignored adapter makes the tuned route and
the base route produce identical answers, and the result would be reported as a
fine-tuned deployment that never ran.

The mitigation is a differential check before any evaluation. `make adapter`
runs `scripts/check_adapter.py`, which sends the same snapshots to both routes
and fails if the outputs match. If they match token for token across several
inputs, the adapter is not applied, and the honest recoveries are to merge the
adapter into the base weights and serve the merged model, to serve through
Unsloth `FastModel`, or to fall back to Gemma 3, which has working vLLM LoRA
support.

Note also that the 26B A4B is a mixture of experts and the 12B is encoder-free
multimodal. Both are the awkward cases for adapter serving. A dense text model
is the lower-risk choice for a one-day build.

## Lambda

- Pricing: [lambda.ai/pricing](https://lambda.ai/pricing)
- On-demand cloud docs: [docs.lambda.ai](https://docs.lambda.ai/)

Self serve, first-come access, no minimum commitment.

| GPU | VRAM | vCPUs | USD per GPU hour |
|---|---|---|---|
| B200 SXM6 | 180 GB | 208 | 6.69 |
| H100 SXM | 80 GB | 208 | 3.99 |
| A100 SXM | 80 GB | 240 | 2.79 |
| A100 SXM | 40 GB | 124 | 1.99 |
| Tesla V100 | 16 GB | 88 | 0.79 |

Prices exclude tax. Storage runs 5.8 to 22 TiB SSD depending on instance.

A single A100 80 GB is the sane default for a small Gemma under QLoRA. Do not
quote a total before the instance and any event credits are known. Training and
serving on one GPU compete for memory, so stage them rather than running both.

## Respan

- Product: [respan.ai](https://respan.ai)
- Docs: [respan.ai/docs](https://respan.ai/docs)
- Custom models: [gateway/custom-models](https://www.respan.ai/docs/documentation/features/gateway/custom-models)
- Span attributes: [reference/span-attributes](https://www.respan.ai/docs/documentation/resources/reference/span-attributes)
- Evaluations quickstart: [evals/quickstart](https://www.respan.ai/docs/documentation/features/evals/quickstart)

A unified LLM engineering platform covering a gateway, tracing, evaluations and
monitoring. Traces capture each call as spans with input, output, latency and
cost. Evaluators combine AI judges, deterministic checks and human review.

Custom models are added through the UI: Models page, "Create custom model",
then a form for name, provider, costs and modality. The public docs do not state
the fields for a self-hosted OpenAI-compatible base URL, and the custom models
page says a custom model has to map to a valid provider model. That is not the
same as registering an arbitrary endpoint.

**Treat this as unresolved.** Confirm before committing that a self-hosted
endpoint can be registered as a provider. If it cannot, the fallback is to log
traces directly with the same attributes `serving/respan.py` already attaches,
which preserves the traceability requirement without the gateway.

Self-hosted GPU cost is not in a token log. Allocate it separately.

## Nango

- Google Sheets integration: [docs.nango.dev/integrations/all/google-sheet](https://docs.nango.dev/integrations/all/google-sheet)
- Integration catalog: [docs.nango.dev/integrations](https://docs.nango.dev/integrations)
- Documentation home: [docs.nango.dev](https://docs.nango.dev)

The Google Sheets integration needs the
`https://www.googleapis.com/auth/spreadsheets` scope.

The integration page states there is no setup guide yet and no pre-built use
cases. There is therefore no ready-made read-rows or append-row action, and
everything goes through the generic proxy against the
[Google Sheets API](https://developers.google.com/sheets/api/reference/rest),
with local code doing row mapping, matching on `incident_id`, and validation.

That is what `review/nango_sheet.py` assumes, which is why its two network
functions raise `NotImplementedError`. It does mean the review loop is more work
than it first appears, and it is a reasonable thing to cut under time pressure.
A local CSV plus a manual import preserves the round trip for a demo.

## Order of operations

1. Pick a Gemma 4 checkpoint, dense and small, and pin the revision.
2. Stand up vLLM with the adapter and run `make adapter`. Settle the silent
   adapter question first, because everything downstream depends on it.
3. Confirm whether Respan accepts a self-hosted endpoint as a provider.
4. Create the Nango Google Sheets connection and prove one write and one read
   through the proxy.
5. Only then size the GPU instance and estimate cost from measured memory and
   throughput.
