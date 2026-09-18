# Memory/context management harness

The layer that decides what goes into the model's limited context window on each turn — summarizing old turns, retrieving relevant past state, evicting stale content — since raw conversation history alone doesn't scale past a few dozen turns.
