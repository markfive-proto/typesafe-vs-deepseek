# LLM inference serving

The systems layer (vLLM, TGI, and similar) that turns a trained model into a request-serving API, handling request batching, memory management, and scheduling to maximize throughput per GPU rather than serving one request at a time.
