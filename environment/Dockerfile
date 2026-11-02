# hash:sha256:d5924041de6e6f776353c8d9e61cb624f3b3d9c5a167f505315824ba225e3cc4
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/mambaforge3:24.5.0-0-python3.12.4-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG GIT_ASKPASS
COPY git-ask-pass /

RUN --mount=type=secret,id=git-access-token \
    GIT_ACCESS_TOKEN="$(cat /run/secrets/git-access-token)" \
    pip3 install -U --no-cache-dir \
    -e git+https://github.com/AllenNeuralDynamics/aind-ophys-dff-library.git@c1d2b1f#egg=aind-ophys-dff-library
