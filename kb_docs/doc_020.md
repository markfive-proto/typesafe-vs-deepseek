# Speculative decoding

Using a small, fast draft model to propose several tokens ahead, which the large model then verifies in parallel — sound tokens are accepted, wrong ones are recomputed — cutting latency without changing output quality.
