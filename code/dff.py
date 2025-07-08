import argparse
import json
import logging
import os
from datetime import datetime as dt
from pathlib import Path
from typing import Union

import aind_ophys_utils.dff as dff
import h5py
from aind_data_schema.core.processing import DataProcess, ProcessName
from aind_log_utils.log import setup_logging
from pydantic import Field
from pydantic_settings import BaseSettings
from scipy.stats import skew


class DFFSettings(BaseSettings, cli_parse_args=True):
    """Settings for DF/F calculation parameters"""

    input_dir: Path = Field(
        default="/data",
        description="Input directory containing raw movies and metadata files",
    )
    output_dir: Path = Field(
        default="/results", description="Output director where to save results to"
    )
    long_window: int = Field(
        default=60,
        description="Moving window size (in seconds) of the rolling percentile filter used to compute a rolling baseline",
    )
    short_window: float = Field(
        default=3.333,
        description="Moving window size (in seconds) of the median filter to compute the rolling median-filtered signal, which is subtracted from the input 'F' for noise_method=mad",
    )
    inactive_percentile: int = Field(
        default=10,
        description="Percentile value that defines the inactive frames used for calculating the baseline",
    )
    noise_method: str = Field(
        default="mad",
        description="Method for computing the noise, see ..signal_utils.noise_stdChoices: 'mad', 'fft', 'welch'",
    )

    class Config:
        env_prefix = "DFF_"


def write_data_process(
    metadata: dict,
    input_fp: Union[str, Path],
    output_fp: Union[str, Path],
    unique_id: str,
    start_time: dt,
    end_time: dt,
) -> None:
    """Writes output metadata to plane processing.json

    Parameters
    ----------
    metadata: dict
        parameters from suite2p motion correction
    input_fp: str
        path to raw movies
    output_fp: str
        path to motion corrected movies
    unique_id: str
        unique identifier
    start_time: dt
        start time of processing
    end_time: dt
        end time of processing
    """
    data_proc = DataProcess(
        name=ProcessName.DF_F_ESTIMATION,
        software_version=os.getenv("VERSION", ""),
        start_date_time=start_time.isoformat(),
        end_date_time=end_time.isoformat(),
        input_location=str(input_fp),
        output_location=str(output_fp),
        code_url=(os.getenv("REPO_URL", "")),
        parameters=metadata,
    )
    if isinstance(output_fp, str):
        output_dir = Path(output_fp).parent
    else:
        output_dir = output_fp.parent
    with open(output_dir / f"{unique_id}_df_f_data_process.json", "w") as f:
        json.dump(json.loads(data_proc.model_dump_json()), f, indent=4)


def get_metadata(input_dir: Path, meta_type: str) -> dict:
    """Extracts metadata from processing and subject json files

    Parameters
    ----------
    input_dir: Path
        input directory
    meta_type: str
        type of metadata to extract

    Returns
    -------
    metadata: dict
        metadata
    """
    input_fp = next(input_dir.rglob(f"{meta_type}"), "")
    if not input_fp:
        raise FileNotFoundError(f"No {meta_type} file found in {input_dir}")
    with open(input_fp, "r") as f:
        metadata = json.load(f)
    return metadata


def make_output_directory(output_dir: Path, experiment_id: str) -> str:
    """Creates the output directory if it does not exist

    Parameters
    ----------
    output_dir: Path
        output directory
    experiment_id: str
        experiment_id number

    Returns
    -------
    output_dir: str
        output directory
    """
    output_dir = output_dir / experiment_id
    output_dir.mkdir(exist_ok=True)
    output_dir = output_dir / "dff"
    output_dir.mkdir(exist_ok=True)

    return output_dir


if __name__ == "__main__":
    start_time = dt.now()
    args = DFFSettings()
    input_dir = args.input_dir
    output_dir = args.output_dir
    data_description_data = get_metadata(input_dir, "data_description.json")
    name = data_description_data.get("name", "")
    subject_data = get_metadata(input_dir, "subject.json")
    subject_id = subject_data.get("subject_id", "")
    setup_logging("aind-ophys-dff", mouse_id=subject_id, session_name=name)
    extraction_dir = next(input_dir.rglob("*/extraction"))
    experiment_id = extraction_dir.parent.name
    logging.info(f"Calculating dF/F for ExperimentID {experiment_id}")
    extraction_fp = next(extraction_dir.glob("*extraction.h5"))
    output_dir = make_output_directory(output_dir, experiment_id)
    with h5py.File(extraction_fp, "r") as f:
        traces = f["traces/corrected"][()]
    if len(traces):
        # Pass settings parameters to the dff function
        dff_traces, baseline, noise = dff.dff(
            traces,
            long_window=args.long_window,
            short_window=args.short_window,
            inactive_percentile=args.inactive_percentile,
            noise_method=args.noise_method,
        )
    else:  # no ROIs detected
        dff_traces, baseline, noise = traces, traces, []
    skewness = skew(dff_traces, axis=1)
    with h5py.File(output_dir / f"{experiment_id}_dff.h5", "w") as f:
        f.create_dataset("data", data=dff_traces)
        f.create_dataset("baseline", data=baseline)
        f.create_dataset("noise", data=noise)
        f.create_dataset("skewness", data=skewness)

    # Include settings in metadata
    input_params = {**vars(args)}
    write_data_process(
        input_params,
        extraction_fp,
        output_dir / "dff.h5",
        experiment_id,
        start_time,
        dt.now(),
    )
