# Retry and error-recovery harness

Logic that catches tool failures, malformed model output, or transient API errors and retries with backoff or a repaired prompt, rather than letting the whole agent run crash on the first hiccup.
