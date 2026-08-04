# Container image for course-chatbot's Bot Framework front door, built by the pipeline's ARM
# CodeBuild project (pipeline/codebuild.yml) with CONTAINER_TARGET=course-chatbot and
# CONTAINER_CONTEXT=blueprints/course-chatbot -- see "Adding a container image build" in
# pipeline/README.md. The build context is THIS directory, so COPY paths are relative to it.
# Keep the named target: CONTAINER_TARGET selects it.
#
# There is no root Dockerfile in this repository (CLAUDE.md). Each component keeps its own
# here, and the Build action's CONTAINER_CONTEXT must agree with where the component lives --
# a stale context fails with a missing-path error that says nothing about the move.

# --- course-chatbot: Bot Framework front door -------------------------------------------
# Lambda container contract: the AWS base image provides the runtime interface client, the
# handler lands in ${LAMBDA_TASK_ROOT}, and CMD names it. Built for linux/arm64 to match the
# function's Architectures.
#
# This base image, NOT the uv image builder-mcp uses: requirements.txt deliberately omits
# boto3 because the AWS Lambda Python base image ships it. Switching bases would break that
# assumption silently.
FROM public.ecr.aws/lambda/python:3.13 AS course-chatbot

# Dependencies first, so a handler edit does not re-resolve the dependency layer.
COPY src/requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN python -m pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY src/handler.py ${LAMBDA_TASK_ROOT}/handler.py
COPY src/botframework.py ${LAMBDA_TASK_ROOT}/botframework.py

CMD ["handler.handler"]
