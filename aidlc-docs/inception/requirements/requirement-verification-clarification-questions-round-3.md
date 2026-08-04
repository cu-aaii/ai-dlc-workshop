# Requirements Clarification Questions — Round 3

Resolving Round 2 reopened one earlier answer. This is (hopefully) the last round before I draft
`requirements.md`.

## Contradiction 3: IAM-authenticated API vs. a browser-based web UI
Round 2 settled on **IAM-authenticated API calls only** for v1 (no Cognito, no public login) —
which matches the original Q5 option C: "internal only, e.g. workshop organizers query it directly
(CLI/API with IAM auth)". But Round 1's Q3 chose **a web UI** (S3 + CloudFront static site calling
the API).

Those two don't fit together cleanly: a browser has no natural way to attach IAM SigV4 credentials
to its requests, so a *public* web page can't call an IAM-authenticated API. The usual ways to make
that work are either (a) restrict the UI to people who already have AWS credentials configured
locally — which mostly defeats the point of having a UI instead of just using the CLI/API directly —
or (b) add some form of identity broker in front of IAM (Cognito Identity Pool, SigV4-signing proxy,
etc.), which reintroduces the auth-infrastructure question Round 2 just deferred.

### Clarification Question 3
How should v1 actually be consumed, given IAM-auth-only was the answer to Round 2?

A) Drop the web UI for v1 — CLI/API only, IAM-authenticated, exactly matching the original Q5
   option C. Add a UI later once real auth (Cognito, possibly Entra-federated) exists

B) Keep a browser UI, but scope it to people who already have AWS credentials — e.g. a static
   page that runs signed requests using credentials the viewer supplies themselves (from `aws
   configure`/SSO), effectively a browser-based CLI substitute rather than a public dashboard

C) Add a minimal Cognito Identity Pool now (not a user pool/login — just IAM-role vending for the
   browser session) so the static site can call the API without a full auth system or the Entra
   dependency Round 2 avoided

X) Other (please describe after [Answer]: tag below)

[Answer]:Deploy to an internal subnet that has no public access
