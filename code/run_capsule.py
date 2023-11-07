import os
import argparse
from pathlib import Path
import glob
import shutil
import aind_ophys_utils.dff as dff
from scipy.stats import skew
import h5py as h5


def make_output_directory(output_dir: str, experiment_id: str = None) -> str:
    """Creates the output directory if it does not exist

    Parameters
    ----------
    output_dir: str
        output directory
    experiment_id: str
        experiment_id number

    Returns
    -------
    output_dir: str
        output directory
    """
    if experiment_id:
        output_dir = os.path.join(output_dir, experiment_id)
    else:
        output_dir = os.path.join(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    return Path(output_dir)


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

    args = parser.parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    neuropil_trace_fp = [
        i for i in list(input_dir.glob("*/*")) if "neuropil_correction.h5" in str(i)
    ][0]
    motion_corrected_fn = [i for i in list(input_dir.glob("*/*")) if "decrosstalk.h5" in str(i)][0]
    experiment_id = motion_corrected_fn.name.split("_")[0]
    output_dir = make_output_directory(output_dir, experiment_id)
    process_json = [i for i in list(input_dir.glob("*/*")) if "processing.json" in str(i)][0]
    with h5.File(neuropil_trace_fp, "r") as f:
        neuropil_corrected = f["data"][()]
        roi_names = f["roi_names"][()]
    dff_traces, baseline, noise = dff(neuropil_corrected)
    skewness = skew(dff_traces, axis=1)
    with h5.File(output_dir / "dff.h5", "w") as f:
        f.create_dataset("data", data=dff_traces)
        f.create_dataset("baseline", data=baseline)
        f.create_dataset("noise", data=noise)
        f.create_dataset("skewness", data=skewness)
        f.create_dataset("roi_names", data=roi_names)
    # This will be removed when I update the metadata and clean up the copy mess
    copy_data_to_results(input_dir, output_dir)
