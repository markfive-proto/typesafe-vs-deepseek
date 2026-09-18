# Agent SDK tool-use loop

The library-level abstraction for the read-decide-act loop: pass the model a set of tool definitions, execute whichever tool call it returns, feed the result back, repeat until a stop condition. Most agent frameworks are a thin layer over this loop.
