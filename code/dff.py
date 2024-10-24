import argparse
import json
import os
from datetime import datetime as dt
from pathlib import Path
from typing import Union

import aind_ophys_utils.dff as dff
import h5py
import numpy as np
from aind_data_schema.core.processing import (DataProcess, PipelineProcess,
                                              Processing, ProcessName)
from scipy.stats import skew


def write_output_metadata(
    metadata: dict,
    process_json_dir: str,
    process_name: str,
    input_fp: Union[str, Path],
    output_fp: Union[str, Path],
    start_date_time: dt,
) -> None:
    """Writes output metadata to plane processing.json

    Parameters
    ----------
    metadata: dict
        parameters from suite2p motion correction
    input_fp: str
        path to data input
    output_fp: str
        path to data output
    """
    with open(Path(process_json_dir) / "processing.json", "r") as f:
        proc_data = json.load(f)
    processing = Processing(
        processing_pipeline=PipelineProcess(
            processor_full_name="Multplane Ophys Processing Pipeline",
            pipeline_url=os.getenv("PIPELINE_URL", ""),
            pipeline_version=os.getenv("PIPELINE_VERSION", ""),
            data_processes=[
                DataProcess(
                    name=process_name,
                    software_version=os.getenv("VERSION", ""),
                    start_date_time=start_date_time,
                    end_date_time=dt.now(),
                    input_location=str(input_fp),
                    output_location=str(output_fp),
                    code_url=(os.getenv("DFF_EXTRACTION_URL")),
                    parameters=metadata,
                )
            ],
        )
    )
    prev_processing = Processing(**proc_data)
    prev_processing.processing_pipeline.data_processes.append(
        processing.processing_pipeline.data_processes[0]
    )
    prev_processing.write_standard_file(output_directory=Path(output_fp).parent)


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
    extraction_dir = next(input_dir.glob("*/extraction"))
    experiment_id = extraction_dir.parent.name
    print(f"Calculating dF/F for ExperimentID {experiment_id}")
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

    write_output_metadata(
        vars(args),
        extraction_dir,
        ProcessName.DFF_ESTIMATION,
        extraction_fp,
        output_dir / "dff.h5",
        start_time,
    )
