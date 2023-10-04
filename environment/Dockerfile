FROM registry.codeocean.allenneuraldynamics.org/codeocean/jupyterlab:3.4.4-miniconda4.12.0-python3.9-ubuntu20.04

ARG DEBIAN_FRONTEND=noninteractive

ARG GIT_ASKPASS
ARG GIT_ACCESS_TOKEN
COPY git-askpass /

ARG OPHYS_ETL_TAG=main
ARG OPHYS_ETL_COMMIT_SHA="unknown build"

ENV OPHYS_ETL_COMMIT_SHA=${OPHYS_ETL_COMMIT_SHA}
ENV CONDA_ENVS=/opt/conda/envs
ENV OPHYS_ETL_ENV=${CONDA_ENVS}/ophys_etl


# NOTE: To install into conda environments during docker build we need to
# use "conda run -n <my_env> subsequent commands". For details see:
# https://pythonspeed.com/articles/activate-conda-dockerfile/

# Install Suite2P (into conda environment named suite2p)
RUN ["apt-get", "update"]
RUN ["apt-get", "install", "-y", "vim"]
WORKDIR /repos
RUN apt-get -y update --allow-releaseinfo-change \
    && git clone -b ${OPHYS_ETL_TAG} https://github.com/AllenInstitute/ophys_etl_pipelines ./ophys_etl \
    && conda create --prefix ${OPHYS_ETL_ENV} python=3.8 \

    && conda run --prefix ${OPHYS_ETL_ENV} pip install --no-cache ./ophys_etl \
    && conda run --prefix ${OPHYS_ETL_ENV} pip install aind-ophys-utils \