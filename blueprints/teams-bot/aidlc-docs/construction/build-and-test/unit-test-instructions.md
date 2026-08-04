# Unit test instructions — teams-bot

42 tests across two files, `tests/test_botframework.py` and `tests/test_handler.py`. No AWS
credentials, no network, and no container image are needed — they import `src/botframework.py`
and `src/handler.py` directly.

## Run command

From the repo root:

```sh
uv run --python 3.13 --with 'PyJWT[crypto]>=2.8,<3' --with 'anthropic>=0.92,<2' \
    --with boto3 --with pytest pytest blueprints/teams-bot/tests -q
```

Confirmed output:

```
..........................................                               [100%]
42 passed in 0.47s
```

`uv run --python 3.13` fetches an interpreter on demand; the `--with` flags are the same
dependency set the image installs (`PyJWT[crypto]`, `anthropic`, `boto3`), plus `pytest` itself.
Nothing here needs `requirements.lock` directly — the versions above are ranges, matching
`requirements.txt`, because this is a dependency-resolution step for running tests, not the
image build. This is also the command `tools/check` and this blueprint's `README.md` document;
there is one way to run these tests, not several that can drift apart.

**`tools/check` runs this suite — but only since 2026-08-04, and the gap is worth knowing about.**
Until then the PR gate ran `pipeline/stacks.yml` validation, `cfn-lint`, `packages/builder-mcp`'s
own tests and the Terraform checks, and had **no step for `blueprints/teams-bot/tests` at all**. The
42 tests existed, passed, and gated nothing — so "`tools/check` is green" and "the tests pass" were
two separate claims being reported as one, including in this blueprint's own commit messages.

Found by a subagent reading `tools/check` while writing this document, and fixed in the same change
that added it. The lesson generalises: a suite nobody runs automatically is documentation, not a
gate.

Note the dependency versions are duplicated between `tools/check` and the command above. There is no
`pyproject.toml` in this blueprint to resolve a dev group from, so if `requirements.txt`'s ranges
change, both places need editing.

## What each file protects

**`test_botframework.py`** — inbound trust. `botframework.py` imports only `PyJWT` and the
standard library, so this file needs no `boto3`/`anthropic` stub at all, just a locally-generated
RSA keypair and a stubbed JWKS client (`_stub_jwks`, autouse). It covers:

- The happy path (a genuine, correctly-signed activity is accepted), so the rejections below
  mean something.
- **FR-8a specifically**: the `serviceurl` claim must be present and must match the activity
  body's `serviceUrl`, or validation must fail. This is the one property the n8n prototype got
  wrong — it compared `payload.serviceUrl` (camelCase) against a claim actually named
  `serviceurl`, so the check always compared against `None`, and a truthiness guard turned the
  bug into a silent no-op skip rather than a crash. Every other rejection test in this file would
  have passed against that broken code too; `test_absent_serviceurl_claim_is_a_failure` and
  `test_mismatched_serviceurl_is_rejected` are the two that would not have.
- The rest of FR-8: wrong audience, wrong issuer, expired token (and the deliberate leeway
  window), an unsigned/`alg: none` token, a missing or non-`Bearer` `Authorization` header, and
  an unconfigured `BOT_APP_ID` failing closed rather than becoming an open relay.
- Activity parsing: the bot-joining-itself vs. a-human-joining distinction (`28:` prefix
  filtering), an activity with no `text` field, and conversation id/type preservation for channel
  scopes.
- Log-id bounding: the inbound activity id is attacker-controlled *before* authentication runs,
  because the rejection log line is emitted pre-auth. `safe_log_id` is tested for newline
  stripping (log forging), length bounding, never-empty, and — separately — that the *raw* id
  used in Bot Framework API calls is left untouched even when the *logged* copy is sanitized,
  since `|` is legal in a real activity id and stripping it would break replies.

**`test_handler.py`** — the Lambda front door: the always-200 contract, retrieval, and dispatch
routing. It never lets a real `_Runtime` get built — `handler._RUNTIME` is monkeypatched to a
`_StubRuntime` carrying stub `config`/`teams`/`knowledge`/`model` objects, so no real boto3 client
and no real Anthropic client is ever constructed or called. (Only `AWS_REGION`,
`AWS_DEFAULT_REGION`, and `GATEWAY_BASE_URL` are set in the environment, because `handler.py`
builds two module-scope boto3 clients at *import* time — construction alone needs a region, not
credentials.) It covers:

- **`handler()` always returns `{"statusCode": 200}`**, regardless of what fails: a rejected
  token, malformed JSON, an empty event, an oversized body, or an exception raised several calls
  deep inside `_dispatch` (proving the outer `try`/`except` is a real safety net, not just cover
  for the explicitly-handled rejection paths). This is the property the module's own docstring
  calls out as the most important one: a non-200 makes Azure Bot Service retry a request that can
  never succeed, forever (FR-10).
- **`_body()`**: base64-encoded bodies decode correctly, oversized bodies raise, non-object JSON
  (e.g. a bare list) raises.
- **`_retrieve()`**: returns `[]` with no knowledge base configured, returns `[]` (not a raised
  exception) when the retrieval call itself fails, returns passage text on success, filters out
  blank/whitespace-only passages, and truncates an overlong query to `MAX_QUERY_CHARS`.
- **`_dispatch()`**: a human joining gets the greeting, the bot's own join event does not, a real
  message gets a model-generated reply, a textless message and an unrecognized activity type are
  both silently ignored (no send, no reply, no typing indicator).
- **The greeting fallback**: an empty `GREETING_TEXT` environment variable falls back to a
  generic (course-agnostic) greeting rather than an empty string, and a non-empty one is used
  verbatim.

## What this suite deliberately does not cover

- **No AWS.** No real `boto3` client is built or called — SSM, Secrets Manager, S3, and
  `bedrock-agent-runtime` calls are all stubbed. Nothing here proves an IAM policy is correct or
  that a parameter/secret actually resolves at runtime.
- **No network.** No HTTP call reaches Cornell's LiteLLM gateway, the real Bot Framework JWKS
  endpoint, or the Bot Framework API used to send/reply. The `anthropic` client and the Teams
  outbound calls are both stubs (`_StubModel`, `_StubTeams`).
- **No live JWKS fetch.** `test_botframework.py` stubs `bf._jwks_client` to hand back a
  locally-generated key; it never exercises the real network call to Microsoft's JWKS endpoint,
  key rotation, or JWKS-fetch failure handling.
- **No end-to-end path through Teams.** Nothing here drives an actual message from a Teams
  client through Azure Bot Service to the deployed Function URL and back. These tests exercise
  `handler.py`/`botframework.py` as plain Python modules, not the deployed Lambda behind its
  Function URL. That path — Secrets Manager injection, the Azure bot registration, and driving a
  real message through — is covered in `./integration-test-instructions.md`, not here.
- **No container image.** These tests run against `src/` directly; they don't build or exercise
  the Docker image described in `build-instructions.md`.

## Adding a test that fits

- Put JWT/claim/trust logic tests in `test_botframework.py`; anything touching `handler()`,
  `_dispatch`, `_retrieve`, or `_Config` goes in `test_handler.py`.
- Keep the no-AWS, no-network property. If a new code path needs a boto3 or Anthropic call,
  extend the existing stub classes (`_StubKnowledge`, `_StubMessages`, `_StubTeams`) rather than
  reaching for a real client or a mocking library that patches over the network boundary — the
  stubs are shaped to match the one method each real client actually gets called with
  (`retrieve`, `messages.create`, `send`/`reply`/`typing`).
- If the new behavior is a rejection case, assert on `bf.ValidationError` and, where the message
  matters (as with the `serviceurl` cases), assert on the message substring with
  `pytest.raises(..., match=...)` — a rejection test that doesn't check *why* it rejected can pass
  against a wrong implementation for the wrong reason, which is exactly the failure mode
  `test_botframework.py`'s docstring calls out about the n8n prototype.
- If the new behavior changes what reaches Azure Bot Service on failure, add it under the
  "always 200" heading in `test_handler.py` and drive it through `handler.handler(event, None)`
  end-to-end (within the stubbed runtime) rather than unit-testing an inner function in
  isolation — the property being protected is what the outermost boundary returns.
- Re-run the full command above, not just the new test, before committing: both files share
  `sys.path` manipulation at import time (`sys.path.insert(0, ...src)`), and a change to one
  module can affect what the other successfully imports.
