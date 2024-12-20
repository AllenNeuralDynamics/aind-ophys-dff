import argparse
import json
import os
from datetime import datetime as dt
from pathlib import Path
from typing import Union
import logging

import aind_ophys_utils.dff as dff
import h5py
from aind_data_schema.core.processing import DataProcess, ProcessName
from scipy.stats import skew
from aind_log_utils.log import setup_logging


def write_data_process(
    metadata: dict,
    input_fp: Union[str, Path],
    output_fp: Union[str, Path],
    start_time: dt,
    end_time: dt,
) -> None:
    """Writes output metadata to plane processing.json

    Parameters
    ----------
    metadata: dict
        parameters from suite2p motion correction
    raw_movie: str
        path to raw movies
    output_fp: str
        path to motion corrected movies
    """
    data_proc = DataProcess(
        name=ProcessName.DFF_ESTIMATION,
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
    with open(output_dir / "data_process.json", "w") as f:
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
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input-dir", type=str, help="Input directory", default="/data/")
    parser.add_argument(
        "-o", "--output-dir", type=str, help="Output directory", default="/results/"
    )
    start_time = dt.now()
    args = parser.parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    data_description_data = get_metadata(input_dir, "data_description.json")
    name = data_description_data["name"]
    subject_data = get_metadata(input_dir, "subject.json")
    subject_id = subject_data["subject_id"]
    setup_logging("aind-ophys-dff", mouse_id=subject_id, session=name)
    extraction_dir = next(input_dir.glob("*/extraction"))
    experiment_id = extraction_dir.parent.name
    logging.info(f"Calculating dF/F for ExperimentID {experiment_id}")
    extraction_fp = next(extraction_dir.glob("*extraction.h5"))
    output_dir = make_output_directory(output_dir, experiment_id)
    with h5py.File(extraction_fp, "r") as f:
        traces = f["traces/corrected"][()]
    if len(traces):
        dff_traces, baseline, noise = dff.dff(traces)
    else:  # no ROIs detected
        dff_traces, baseline, noise = traces, traces, []
    skewness = skew(dff_traces, axis=1)
    with h5py.File(output_dir / f"{experiment_id}_dff.h5", "w") as f:
        f.create_dataset("data", data=dff_traces)
        f.create_dataset("baseline", data=baseline)
        f.create_dataset("noise", data=noise)
        f.create_dataset("skewness", data=skewness)

    write_data_process(
        vars(args),
        extraction_fp,
        output_dir / "dff.h5",
        start_time,
        dt.now(),
    )
