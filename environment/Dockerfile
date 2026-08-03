FROM python:3.9-slim
ARG DEBIAN_FRONTEND=noninteractive

ENV PIPELINE_URL="https://codeocean.allenneuraldynamics.org/capsule/5619253/tree"
ENV PIPELINE_VERSION="1.0"
ENV VERSION="6.0"


ENV DFF_EXTRACTION_URL=https://github.com/AllenNeuralDynamics/aind-ophys-dff

RUN ["apt-get", "update"]
RUN ["apt-get", "install", "-y", "vim"]
RUN pip3 install -U --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

RUN pip3 install -U --no-cache-dir \
    aind-ophys-utils \
    aind-data-schema==1.2.0 \
    aind-log-utils \
    aind-qcportal-schema \
    matplotlib \
    pydantic==2.8.2 \
    pydantic_settings

RUN mkdir -p /data /results /scratch /capsule/code
COPY code/ /capsule/code
