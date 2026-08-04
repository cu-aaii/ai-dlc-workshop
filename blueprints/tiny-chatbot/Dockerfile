# Container image for tiny-chatbot, built by the pipeline's ARM CodeBuild project
# (pipeline/codebuild.yml) once its Build stage action is wired with
# CONTAINER_TARGET=tiny-chatbot and CONTAINER_CONTEXT=blueprints/tiny-chatbot -- see
# "Adding a container image build" in pipeline/README.md. The build context is this
# directory, so COPY paths are relative to it. Keep the named target: CONTAINER_TARGET
# selects it.

# --- tiny-chatbot: the world's tiniest chatbot, a canned-response Lambda -----------------
# Lambda container contract: the AWS base image provides the runtime interface client, the
# handler lands in ${LAMBDA_TASK_ROOT}, and CMD names it. Built by the ARM CodeBuild
# project (linux/arm64). The blueprint is parked (deployed_by: manual) until its Build
# action is wired; pin this base image by digest (SECURITY-10, like builder-mcp's
# Dockerfile) in the PR that wires the Build action.
FROM public.ecr.aws/lambda/python:3.13 AS tiny-chatbot

COPY src/app.py ${LAMBDA_TASK_ROOT}/app.py

CMD ["app.handler"]
