import os
import argparse
from pathlib import Path
import glob
import shutil
import aind_ophys_utils.dff as dff
from scipy.stats import skew
import h5py as h5
import json
from pathlib import Path
from aind_data_schema.core.processing import Processing, DataProcess, ProcessName, PipelineProcess
from typing import Union
from datetime import datetime as dt
from datetime import timezone as tz


def write_output_metadata(
    metadata: dict,
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
    processing = Processing(
        processing_pipeline=PipelineProcess(
            processor_full_name="Multplane Ophys Processing Pipeline",
            pipeline_url="https://codeocean.allenneuraldynamics.org/capsule/5472403/tree",
            pipeline_version="0.1.0",
            data_processes=[
                DataProcess(
                    name=process_name,
                    software_version=os.getenv("AIND_OPHYS_UTILS_VERSION"),
                    start_date_time=start_date_time,  # TODO: Add actual dt
                    end_date_time=dt.now(tz.utc),  # TODO: Add actual dt
                    input_location=str(input_fp),
                    output_location=str(output_fp),
                    code_url=(os.getenv("AIND_OPHYS_UTILS_REPO_URL")),
                    parameters=metadata,
                )
            ],
        )
    )
    print(f"Output filepath: {output_fp}")
    with open(Path(output_fp).parent.parent / "processing.json", "r") as f:
        proc_data = json.load(f)
    processing.write_standard_file(output_directory=Path(output_fp).parent.parent)
    with open(Path(output_fp).parent.parent / "processing.json", "r") as f:
        dct_data = json.load(f)
    proc_data["processing_pipeline"]["data_processes"].append(
        dct_data["processing_pipeline"]["data_processes"][0]
    )
    with open(Path(output_fp).parent.parent / "processing.json", "w") as f:
        json.dump(proc_data, f, indent=4)


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


def copy_data_to_results(input_dir: str, output_dir: str) -> None:
    """Copy all data from the data directory to the results directory

    Args:
        input_dir (str): path to data directory
        output_dir (str): path to results directory
    """
    files = glob.glob(f"{input_dir}/*")
    for f in files:
        try:
            shutil.copy(f, output_dir)
        except (shutil.SameFileError, IsADirectoryError):
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input-dir", type=str, help="Input directory", default="/data/")
    parser.add_argument(
        "-o", "--output-dir", type=str, help="Output directory", default="/results/"
    )
    start_time = dt.now(tz.utc)
    args = parser.parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    neuropil_trace_fp = next(input_dir.glob("*/trace_extraction/neuropil_traces.h5"))
    motion_corrected_fn = next(input_dir.glob("*/decrosstalk/*decrosstalk.h5"))
    experiment_id = motion_corrected_fn.name.split("_")[0]
    output_dir = make_output_directory(output_dir, experiment_id)
    process_json = next(input_dir.glob("*/processing.json"))
    shutil.copy(process_json, output_dir.parent)
    with h5.File(neuropil_trace_fp, "r") as f:
        neuropil_corrected = f["data"][()]
        roi_names = f["roi_names"][()]
    dff_traces, baseline, noise = dff.dff(neuropil_corrected)
    skewness = skew(dff_traces, axis=1)
    with h5.File(output_dir / "dff.h5", "w") as f:
        f.create_dataset("data", data=dff_traces)
        f.create_dataset("baseline", data=baseline)
        f.create_dataset("noise", data=noise)
        f.create_dataset("skewness", data=skewness)
        f.create_dataset("roi_names", data=roi_names)

    write_output_metadata(
        {
            "skewness": skewness.tolist(),
            "baseline": baseline.tolist(),
            "noise": noise.tolist(),
        },
        ProcessName.DFF_ESTIMATION,
        str(neuropil_trace_fp),
        str(output_dir / "dff.h5"),
        start_time,
    )
    # This will be removed when I update the metadata and clean up the copy mess
