"""
Graph nodes — one node = one file, one public node function per file.

Nodes communicate ONLY through GraphState (no cross-node imports); pure
decision logic stays in the existing agent/ modules the nodes call into.
"""
