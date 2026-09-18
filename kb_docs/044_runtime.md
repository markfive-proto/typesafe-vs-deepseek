# KV cache management

Caching the attention key/value tensors computed for earlier tokens so generating the next token doesn't recompute them from scratch — the dominant memory cost in serving long-context requests, and the reason context length so directly drives infra cost.
