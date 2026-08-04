#!/usr/bin/env bash
#
# The workshop demo, driven from a terminal instead of the Teams bot.
#
# Five scenes: a builder asks for something in plain language, the catalog offers a governed
# blueprint, the Builder MCP plans a deployment, the plan turns out to be a pull request rather
# than a deploy, and -- with account access -- the deployed knowledge base answers a real
# question. Scenes 1-4 need no AWS credentials and mutate nothing. Scene 5 is read-only and
# skips itself, loudly, when there are no credentials.
#
# Every mutating call is dry_run=true. This script cannot open a PR, cannot deploy, and cannot
# delete; that is a property of the tools it calls, not of this script being careful.
#
#   ./demo/demo.sh                 run it
#   ./demo/demo.sh --fast          no pauses (for a rehearsal, or for CI)
#   ./demo/demo.sh --scene 3       one scene only
#   ./demo/demo.sh --list          what the scenes are
#
# Recording it: see demo/README.md.

set -euo pipefail

cd "$(dirname "$0")/.."

# ---------------------------------------------------------------------------- presentation

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  BOLD=$(tput bold); DIM=$(tput dim); RESET=$(tput sgr0)
  BLUE=$(tput setaf 4); GREEN=$(tput setaf 2); YELLOW=$(tput setaf 3); RED=$(tput setaf 1)
else
  BOLD=''; DIM=''; RESET=''; BLUE=''; GREEN=''; YELLOW=''; RED=''
fi

PAUSE=${DEMO_PAUSE:-2}
SCENE_ONLY=''

# One narration line. Deliberately not a typewriter effect -- asciinema replays real timing,
# and fake per-character delays make a recording twice as long for no information.
say()   { printf '\n%s%s%s\n' "$BLUE" "$*" "$RESET"; }
# Continuation line of a say() -- same colour, no blank line, so a sentence that wraps reads as
# one paragraph instead of three.
and()   { printf '%s%s%s\n' "$BLUE" "$*" "$RESET"; }
note()  { printf '%s%s%s\n' "$DIM" "$*" "$RESET"; }
ok()    { printf '%s%s%s\n' "$GREEN" "$*" "$RESET"; }
warn()  { printf '%s%s%s\n' "$YELLOW" "$*" "$RESET"; }
fail()  { printf '%s%s%s\n' "$RED" "$*" "$RESET"; }
beat()  { sleep "$PAUSE"; }

scene() {
  printf '\n%s%s── scene %s ─ %s%s\n' "$BOLD" "$BLUE" "$1" "$2" "$RESET"
}

# Show the command, then run it. The audience needs to see the call, not trust the narration --
# and the echoed line has to be copy-pasteable, so JSON arguments keep their quoting.
run() {
  local shown='' arg
  for arg in "$@"; do
    case "$arg" in
      *[\ \{\}\"\']*) shown="$shown '$arg'" ;;
      *)              shown="$shown $arg" ;;
    esac
  done
  printf '\n%s$%s%s\n' "$BOLD" "$shown" "$RESET"
  beat
  "$@"
}

# ---------------------------------------------------------------------------- scenes

scene_1_ask() {
  scene 1 'a builder asks for something, in their own words'
  note "No AWS account. No console. No Terraform. One sentence in a chat client."
  beat
  run uv run --quiet demo/mcp_call.py blueprint_search \
    '{"query": "a knowledge base I can ask questions about my course documents"}' --ranked
  beat
  say "Ranked, not filtered -- the whole catalog goes to the model, best match first."
  note "Every blueprint here is in the catalog because it has a blueprint.yaml manifest. One"
  note "without a manifest is skipped with no error, so it deploys fine and no builder can be"
  note "offered it: knowledgebase was invisible that way until #15, and this query returned"
  note "tiny-chatbot as its top hit -- a confident wrong answer rather than an empty result."
}

scene_2_contract() {
  scene 2 'the blueprint states its contract up front'
  note "Cost, data classification, what it needs from the builder, what happens on recovery."
  note "The builder chooses with eyes open; the platform team wrote the terms."
  beat
  # The manifest is more comment than contract by line count -- the comments are for the next
  # maintainer, and the contract is what the builder is being shown. Strip them for the demo.
  run bash -c "grep -v '^ *#' blueprints/knowledgebase/blueprint.yaml | grep -v '^ *$'"
  beat
  say "Cost scales with what you store and query -- no idle vector store, which is why a"
  and "managed knowledge base is affordable enough to hand out. The index is declared"
  and "\`derived\`: it rebuilds from the bucket, so it is never the only copy of anything."
  beat
  say "This is the governed part. A builder cannot edit it -- changing it is a PR against the"
  and "blueprint, reviewed by the platform team."
}

scene_3_plan() {
  scene 3 'the MCP plans a deployment -- and only plans it'
  note "dry_run defaults to true. Every mutating tool returns the full plan first."
  beat
  run uv run --quiet demo/mcp_call.py deployment_create \
    '{"blueprint": "knowledgebase", "deployment_name": "knowledgebase", "owner_netid": "aes428", "dry_run": true}'
  beat
  say "Stack name follows <application>-<environment>-<name>, which is what the pipeline role"
  and "is scoped to. Every template parameter is passed explicitly -- no reliance on defaults,"
  and "so it deploys identically by hand and by pipeline."
}

scene_4_gate() {
  scene 4 'the plan is a pull request, not a deployment'
  say "Nothing deployed in scene 3. What the builder got back was a plan and a PR to approve."
  note "main is PR-only by branch protection; the validate check is the automated gate; only"
  note "the ai-dlc-workshop team can merge. The Builder MCP is not on that list, holds no"
  note "CloudFormation write permission, and cannot merge its own pull request."
  beat
  say "Once a human merges, the same MCP reads the whole chain back -- PR, pipeline stages,"
  and "stack status -- so the builder can follow a deploy without an AWS account:"
  beat
  # Degrades to an explanatory note when there are no AWS credentials, which is itself worth
  # showing: the tool reports what it could not reach instead of inventing a status.
  run uv run --quiet demo/mcp_call.py deployment_read '{"deployment_name": "knowledgebase"}'
  beat
  say "That is the whole governance story: the builder never touched AWS, and nothing reached"
  and "the account without a human in the path."
}

scene_5_answer() {
  scene 5 'the deployed knowledge base answers a real question'

  if ! command -v aws >/dev/null 2>&1; then
    warn "SKIPPED: no aws CLI on PATH."
    note "This scene is the only one that needs account access. It is read-only:"
    note "one SSM read and one bedrock-agent-runtime retrieve."
    return 0
  fi
  if ! aws sts get-caller-identity >/dev/null 2>&1; then
    warn "SKIPPED: no AWS credentials in this shell."
    note "Scenes 1-4 are the builder's whole experience, so the demo still lands without this."
    note "To include it, authenticate first and re-run:"
    note "    export AWS_PROFILE=ai-dlc-workshop && aws sso login"
    note ""
    note "What it would run, against the stack the pipeline already deployed:"
    note "    aws ssm get-parameter --name /aidlc/main/knowledgebase/knowledge-base-id"
    note "    aws bedrock-agent-runtime retrieve-and-generate ..."
    return 0
  fi

  local region=${AWS_REGION:-us-east-1}
  local param=/aidlc/${DEMO_ENVIRONMENT:-main}/knowledgebase/knowledge-base-id
  local kb_id

  say "The handoff seam: consumers read the knowledge base id out of SSM, never a CFN export."
  run aws ssm get-parameter --region "$region" --name "$param" --query 'Parameter.Value' --output text
  kb_id=$(aws ssm get-parameter --region "$region" --name "$param" \
    --query 'Parameter.Value' --output text 2>/dev/null || true)

  if [ -z "$kb_id" ] || [ "$kb_id" = 'None' ]; then
    warn "No knowledge base id at $param -- is the stack deployed in this account?"
    note "Scene 5 needs the aidlc-main-knowledgebase stack; the rest of the demo does not."
    return 0
  fi

  local question=${DEMO_QUESTION:-'What is the late homework policy?'}
  say "Now ask it the question a student would ask:"
  note "\"$question\""
  beat
  # retrieve-and-generate, not retrieve: the audience wants the answer, not the chunks.
  run aws bedrock-agent-runtime retrieve-and-generate --region "$region" \
    --input "{\"text\": \"$question\"}" \
    --retrieve-and-generate-configuration \
    "{\"type\":\"KNOWLEDGE_BASE\",\"knowledgeBaseConfiguration\":{\"knowledgeBaseId\":\"$kb_id\",\"modelArn\":\"${DEMO_MODEL_ARN:-arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0}\"}}" \
    --query 'output.text' --output text
  beat
  ok "That answer came from a document a faculty member dropped in a bucket, indexed by a"
  ok "blueprint a builder deployed without ever seeing the AWS console."
}

# ---------------------------------------------------------------------------- driver

list_scenes() {
  cat <<'SCENES'
1  a builder asks for something, in their own words      no credentials needed
2  the blueprint states its contract up front            no credentials needed
3  the MCP plans a deployment -- and only plans it       no credentials needed
4  the plan is a pull request, not a deployment          no credentials needed
5  the deployed knowledge base answers a real question   needs AWS read access
SCENES
}

preflight() {
  if ! command -v uv >/dev/null 2>&1; then
    fail "error: uv is required and was not found."
    note "  macOS:  brew install uv"
    note "  other:  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 127
  fi
  # Warm the server's dependencies before the recording starts, so scene 1 is not a wall of
  # uv download output. Failing here is a real problem worth seeing.
  note "warming up (uv sync, first run only) ..."
  uv run --quiet --directory packages/builder-mcp python -c 'import builder_mcp' >/dev/null
  uv run --quiet demo/mcp_call.py blueprint_search '{"query": "warmup"}' --keys query >/dev/null
  ok "ready"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --fast)  PAUSE=0; shift ;;
    --scene) SCENE_ONLY="$2"; shift 2 ;;
    --list)  list_scenes; exit 0 ;;
    -h|--help)
      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) fail "unknown option: $1"; exit 2 ;;
  esac
done

preflight

printf '\n%s%sCornell AI Platform -- the builder path, end to end%s\n' "$BOLD" "$BLUE" "$RESET"
note "A builder describes what they want. The platform deploys it. The builder never touches AWS."

case "$SCENE_ONLY" in
  '')  scene_1_ask; scene_2_contract; scene_3_plan; scene_4_gate; scene_5_answer ;;
  1)   scene_1_ask ;;
  2)   scene_2_contract ;;
  3)   scene_3_plan ;;
  4)   scene_4_gate ;;
  5)   scene_5_answer ;;
  *)   fail "no scene $SCENE_ONLY (see --list)"; exit 2 ;;
esac

printf '\n%s%s── end%s\n' "$BOLD" "$BLUE" "$RESET"
note "Nothing was deployed, opened, or deleted by this script."
