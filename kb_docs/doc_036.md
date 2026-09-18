# Continuous batching

A scheduling technique that adds new requests into a running batch as soon as GPU slots free up (instead of waiting for a fixed batch to fully finish), substantially raising throughput for variable-length generation workloads.
