# Requirements Clarification Questions — Round 4

Your Round 3 answer ("deploy to an internal subnet that has no public access") resolves the
IAM-vs-browser tension nicely — the security boundary moves to the network instead of forcing IAM
credentials into a browser. One thing needs pinning down before I draft `requirements.md`, though:
I checked `bootstrap/`, `pipeline/`, and `blueprints/` for existing VPC, subnet, VPN, Direct
Connect, or Transit Gateway resources — **there are none in this repo today.**

That matters because "internal subnet" has two very different readings:

- **Literal**: a private VPC subnet, reachable only from Cornell's campus network. That needs real
  network connectivity from this AWS account to campus (VPN, Direct Connect, or Transit Gateway
  peering) — none of which exists yet, and stringing it up is its own significant project, likely
  bigger than the dashboard blueprint itself, and not something achievable inside the workshop.
- **Effective**: "not reachable from the open internet, but not literally inside a VPC either" —
  achievable today, purely in CloudFormation, with CloudFront + an AWS WAF IP-set restricted to
  Cornell's known network ranges (campus + VPN egress IPs). No new networking infrastructure needed.

### Clarification Question 4
Which of these is what you meant?

A) The effective reading — CloudFront + WAF IP-allowlist (Cornell's known ranges). Deployable now,
   no new network infrastructure, still meets "no public access" in the sense that anyone outside
   Cornell's network is blocked

B) The literal reading — a real private VPC subnet reachable only via campus network connectivity.
   Accept that this requires standing up VPN/Direct Connect/Transit Gateway first, as a prerequisite
   piece of work beyond this blueprint (likely out of scope for the workshop timeframe)

X) Other (please describe after [Answer]: tag below)

[Answer]:A
