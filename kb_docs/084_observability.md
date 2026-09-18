# Latency percentile monitoring

Tracking p50/p95/p99 latency rather than just the average, since a handful of very slow requests (often caused by long-context prompts or a struggling downstream provider) can badly hurt user experience while barely moving the mean.
