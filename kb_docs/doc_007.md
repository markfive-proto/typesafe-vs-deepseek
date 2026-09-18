# GPU scheduling for inference

The logic that assigns incoming requests to available GPU capacity, balancing utilization against per-request latency — packing too aggressively increases queueing delay, under-packing wastes expensive hardware.
