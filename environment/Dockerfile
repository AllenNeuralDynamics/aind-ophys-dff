# hash:sha256:ee247fbf0652388380f40600186d0aa151683325b9d9164b654b7b72b4971e64
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/mambaforge3:24.5.0-0-python3.12.4-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG GIT_ASKPASS
COPY git-ask-pass /

RUN --mount=type=secret,id=git-access-token \
    GIT_ACCESS_TOKEN="$(cat /run/secrets/git-access-token)" \
    pip3 install -U --no-cache-dir \
    aind-data-schema==1.2.0 \
    aind-log-utils==0.2.8 \
    aind-qcportal-schema==0.3.2 \
    matplotlib==3.9.4 \
    pydantic==2.8.2 \
    pydantic-settings==2.11.0 \
    -e git+https://github.com/AllenNeuralDynamics/aind-ophys-utils.git@48489e7f964bae6226621a1f3c483c43239d94b2#egg=aind-ophys-utils
