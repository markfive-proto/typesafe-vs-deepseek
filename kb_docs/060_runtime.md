# Distributed inference (tensor/pipeline parallelism)

Splitting a single model too large for one GPU across multiple GPUs (or nodes), either by layer (pipeline parallelism) or within a layer (tensor parallelism), each with different communication overhead and latency tradeoffs.
