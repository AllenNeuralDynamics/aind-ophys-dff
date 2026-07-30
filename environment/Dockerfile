# hash:sha256:8424b003493e6ba3229fecb937da94fdaf147044ea10cd8faaddf2d0a390bb1a
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/mambaforge3:24.5.0-0-python3.12.4-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG GIT_ASKPASS
COPY git-ask-pass /

RUN --mount=type=secret,id=git-access-token \
    GIT_ACCESS_TOKEN="$(cat /run/secrets/git-access-token)" \
    pip3 install -U --no-cache-dir \
    -e git+https://github.com/AllenNeuralDynamics/aind-ophys-dff-library.git@30adece1357e90fc36418003f0661a6225788851#egg=aind-ophys-dff-library
