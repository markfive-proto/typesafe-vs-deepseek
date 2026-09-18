# Prompt caching at the runtime layer

Reusing the computed KV cache for a repeated prompt prefix (a long system prompt, a shared document) across requests so only the new suffix needs fresh computation — the mechanism behind 'cached input token' pricing discounts.
