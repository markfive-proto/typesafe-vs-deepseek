# Serverless inference cold starts

The latency penalty of loading a large model into GPU memory when a serverless function scales from zero, a problem specific to LLM serving because model weights are gigabytes, unlike a typical stateless web function.
