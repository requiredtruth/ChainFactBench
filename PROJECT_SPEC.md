# ChainFactBench 0.1.1 Specification

## Outcome

Provide a zero-runtime-dependency Python CLI that captures allowlisted read-only EVM JSON-RPC results at an explicit block and deterministically scores structured AI answers against the frozen values and block evidence.

## Invariants

- No wallet connection, key, seed phrase, signature, transaction submission, trade, approval, or custody path exists.
- Capture accepts only the read-only method allowlist in source.
- Mutable block tags are rejected before network access.
- The block header is checked before and after case capture; a hash change aborts output.
- RPC endpoints are neither persisted nor printed.
- Bundles and reports use stable schemas and canonical JSON hashing.
- Failed evidence and failed values are reported separately.
- Synthetic examples make no live-chain claim.

## Interfaces

| Command | Contract |
|---|---|
| `verify BUNDLE` | Validate schema, bounds, pinned block parameters, and expected-value digests |
| `capture SPEC OUTPUT` | Perform bounded allowlisted reads and atomically write one frozen bundle |
| `prompts BUNDLE [OUTPUT]` | Emit answer-ready JSONL without expected values |
| `score BUNDLE ANSWERS` | Produce deterministic table or JSON scoring and meaningful exit status |
| `demo` | Run the synthetic offline end-to-end scoring path |
| `run.sh` | Install when needed and open the PySide6 control panel |
| `cli.sh` | Run the CLI from any working directory |
| `demo.sh` | Run the bundled offline demonstration |
| `test.sh` | Run deterministic syntax and behavior checks |

## Acceptance evidence

- Python compilation succeeds.
- Unit tests cover valid, malformed, mutable-tag, tampered-digest, duplicate, missing, wrong-value, and wrong-evidence inputs.
- Mock-RPC integration proves the call sequence is read-only and the header is rechecked.
- CLI tests prove machine-readable verification, expected-value-free prompts, failure exit status, and no redirected ANSI output.
- A prepared copy passes `./demo.sh` and `./test.sh` without a network request.
- Release files contain the exact authorized support addresses and no secret material.

## Non-goals

- Running models or interpreting prose.
- Live monitoring, wallet analysis, transaction creation, or trading.
- Declaring addresses or contracts malicious.
- Replacing an Ethereum client, explorer, or RPC load tester.
