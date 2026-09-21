# Offline query evaluations

Run `python3 tests/eval/run_eval.py` from any directory. The YAML cases specify
exact argument lists, stdout (or required/forbidden substrings), and exit
codes. Queries run against the v4.1 reference with `MEMORY_TODAY=2026-09-21`.
`--vault PATH` evaluates a disposable copy, useful for negative gate tests.

This is a deterministic protocol/retrieval contract, not a language-model
benchmark. Latency is informative only, not a flaky timing threshold.
No downloads, model calls, or additional dependencies beyond PyYAML.
The optional LongMemEval conversion adapter is deferred; semantic reasoning
and answer-generation benchmarks are outside this reference's scope.
