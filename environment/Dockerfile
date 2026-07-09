# hash:sha256:0e951733d816fe6b42cbaffc702a88a983e354f0131ce0b6bc1ec64499b500e5
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/mambaforge3:24.5.0-0-python3.12.4-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive

ENV PIPELINE_URL="https://codeocean.allenneuraldynamics.org/capsule/5619253/tree"
ENV VERSION="6.0"

ARG GIT_ASKPASS
ARG GIT_ACCESS_TOKEN
COPY git-ask-pass /

ENV DFF_EXTRACTION_URL=https://github.com/AllenNeuralDynamics/aind-ophys-dff

RUN pip3 install -U --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    # aind-ophys-utils \
    git+https://github.com/AllenNeuralDynamics/aind-ophys-utils.git@plot-dff-style  \
    aind-data-schema==1.2.0 \
    aind-log-utils \
    aind-qcportal-schema \
    matplotlib \
    pydantic==2.8.2 \
    pydantic_settings