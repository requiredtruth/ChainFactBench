# ChainFactBench

**Block-pinned evaluation of AI answers against deterministic EVM JSON-RPC facts.**

ChainFactBench captures allowlisted read-only chain facts at an explicit block, verifies that the block hash remains stable during capture, freezes canonical expected values with SHA-256 digests, and scores structured model answers offline. It does not connect a wallet, sign, submit transactions, trade, or call a hosted model.

## Why this exists

An answer such as “the balance is 42” is not reproducible unless it names the chain state it used. `latest`, `safe`, and `finalized` move over time. ChainFactBench requires an explicit block number and binds every case to the observed block hash, so a result can be rerun and audited.

This is not another RPC throughput benchmark:

| Tool category | Primary job | ChainFactBench distinction |
|---|---|---|
| [Chainbench](https://github.com/chainstacklabs/chainbench) | Load-test blockchain infrastructure | Scores AI answers, not node throughput |
| General LLM evaluation harnesses | Run model tasks and aggregate metrics | Uses EVM-aware block evidence and exact chain-value evaluators |
| Explorer/API wrappers | Retrieve current or historical values | Produces portable frozen bundles and offline scoring |

The format follows [EIP-1474 quantity and block-identifier rules](https://eips.ethereum.org/EIPS/eip-1474). Exact-name GitHub search found no other public `ChainFactBench` repository when 0.1.0 was prepared. That is a naming fact, not a claim that chain evaluation itself has no prior art.

## One-command verification

Python 3.10+ and the standard library are sufficient:

```bash
./install.sh
```

Expected final output:

```text
synthetic-balance  PASS    exact
synthetic-code     PASS    exact
score=2/2 (100.00%) unexpected=0
```

The bundled demonstration is synthetic and performs no network request.

## Workflow

### 1. Define cases

Copy [`examples/capture_spec.json`](examples/capture_spec.json). Every method must be on the read-only allowlist and its block parameter must be exactly `$BLOCK`.

```json
{
  "schema_version": 1,
  "block_number": "0x10",
  "cases": [
    {
      "id": "account-balance",
      "prompt": "Report the account balance at the supplied pinned block.",
      "method": "eth_getBalance",
      "params": ["0x0000000000000000000000000000000000000001", "$BLOCK"],
      "evaluator": "quantity"
    }
  ]
}
```

Allowed methods are `eth_getBalance`, `eth_getBlockByNumber`, `eth_getBlockTransactionCountByNumber`, `eth_getCode`, `eth_getProof`, `eth_getStorageAt`, `eth_getTransactionCount`, and `eth_call`. There is no send, signing, filter, subscription, or wallet method.

### 2. Capture a frozen bundle

Prefer the environment variable so an endpoint containing a provider token is not placed in shell history:

```bash
export CHAINFACT_RPC_URL='YOUR_READ_ONLY_RPC_ENDPOINT'
./run.sh capture examples/capture_spec.json evidence.json
```

The endpoint is used in memory and is never written to the bundle or printed. Capture resolves `eth_chainId`, reads the block header, performs the cases with the explicit block number, then reads the header again. A changed hash aborts the capture.

### 3. Produce model prompts

```bash
./run.sh prompts evidence.json prompts.jsonl
```

Prompt rows include the pinned evidence fields and required answer shape, but not expected values. Feed them to any local or external model under your own privacy policy. ChainFactBench itself makes no model request.

Each answer is one JSON object per line:

```json
{"case_id":"account-balance","block_number":"0x10","block_hash":"0x...","value":"42"}
```

### 4. Score offline

```bash
./run.sh verify evidence.json
./run.sh score evidence.json answers.jsonl --no-color
./run.sh score evidence.json answers.jsonl --format json
```

Exit codes:

- `0` — valid input and every expected case passed;
- `1` — valid scoring input with one or more failed cases, or an RPC transport/server failure;
- `2` — invalid arguments, schema, encoding, bounds, or files.

## Evaluators

- `quantity` compares a canonical RPC quantity to a non-negative answer expressed as an integer, decimal string, or minimal `0x` quantity.
- `json_exact` compares canonical sorted JSON, preserving type distinctions such as string versus integer.

Every answer must also reproduce the bundle's block number and block hash. A correct value with wrong evidence fails.

## Stable errors handled

```text
error: cases[0].params[1] contains mutable block tag 'latest'
error: cases[0].expected_sha256 does not match expected
error: pinned block hash changed during capture; discard and retry
error: RPC transport failed (URLError)
```

Input files, JSONL lines, case counts, prompts, timeouts, and RPC responses are bounded. Outputs are deterministic and sorted. ANSI color is used only on an interactive terminal and is disabled by `--no-color`, `NO_COLOR`, or redirection.

## Limitations

- EVM JSON-RPC only in 0.1.0.
- The capture endpoint is trusted for the values it returns; cross-node quorum verification is not implemented.
- Header reorganization is detected during capture, not continuously afterward.
- Historical state requires a node that retains the requested block.
- Scoring expects structured JSONL, not subjective free-form answer parsing.
- Evidence bundles contain expected values. Keep evaluation bundles private until a run is complete when answer leakage matters.
- No profitability, security-label, malicious-address, or investment conclusion is produced.

## Repository layout

```text
chainfactbench/     typed capture, validation, RPC, scoring, and CLI modules
examples/           synthetic bundle, answers, and capture specification
tests/              unit, CLI, mock-RPC integration, and release-boundary tests
install.sh             syntax, full test suite, and offline end-to-end demo
run.sh              location-independent CLI launcher
PROJECT_SPEC.md     stable scope and acceptance contract
```

## Support development

Donations fund additional production. After a transaction is confirmed, a donor may open the funded-direction issue template with the asset, exact network, public transaction hash, and requested benchmark direction. See [`SUPPORT.md`](SUPPORT.md) for the exact addresses and boundaries.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
