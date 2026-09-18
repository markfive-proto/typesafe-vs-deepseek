# Function/tool-calling harness

The layer that turns a model's structured tool-call output into an actual function invocation, validates arguments against a schema, executes it, and serializes the result back into the conversation in the format the model expects.
