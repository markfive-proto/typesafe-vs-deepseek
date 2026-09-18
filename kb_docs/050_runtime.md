# Multi-model serving (model mesh)

Infrastructure that hosts many different models behind one serving layer, dynamically loading/evicting them from GPU memory based on demand, so low-traffic models don't each need dedicated, idle hardware.
