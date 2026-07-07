# hash:sha256:c9937fdf4903ca5b6b1c314fe3e02282f1686c25472e5d795f6ced4b1f96fdf3
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/mambaforge3:24.5.0-0-python3.12.4-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG GIT_ASKPASS
COPY git-ask-pass /

RUN --mount=type=secret,id=git-access-token \
    GIT_ACCESS_TOKEN="$(cat /run/secrets/git-access-token)" \
    pip3 install -U --no-cache-dir \
    aind-data-schema==1.2.0 \
    aind-data-schema-models==0.7.5 \
    aind-log-utils==0.2.8 \
    aind-qcportal-schema==0.4.0 \
    matplotlib==3.10.9 \
    pydantic-settings==2.14.1 \
    -e git+https://github.com/AllenNeuralDynamics/aind-ophys-dff-library.git@v0.1.0#egg=aind-ophys-dff-library
