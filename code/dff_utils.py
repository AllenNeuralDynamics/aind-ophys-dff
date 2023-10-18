import os
import argparse
import json
from pathlib import Path
import glob
import shutil


def make_output_directory(output_dir: str, experiment_id: str=None) -> str:
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
    # Generate input json
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input-dir", type=str, help="Input directory", default="/data/")
    parser.add_argument("-o", "--output-dir", type=str, help="Output directory", default="/results/")
    
    args = parser.parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    neuropil_trace_fp = [i for  i in list(input_dir.glob("*/*")) if "neuropil_correction.h5" in str(i)][0]
    motion_corrected_fn = [i for i in list(input_dir.glob("*/*")) if "decrosstalk.h5" in str(i)][0]
    experiment_id = motion_corrected_fn.name.split("_")[0]
    output_dir = make_output_directory(output_dir, experiment_id)
    process_json = [i for  i in list(input_dir.glob("*/*")) if "processing.json" in str(i)][0]
    with open(process_json, "r") as j:
        data = json.load(j)
    frame_rate = data["data_processes"][0]["parameters"]["movie_frame_rate_hz"]
    input_data = {
        "input_file": str(neuropil_trace_fp),
        "output_file": str(output_dir / "dff.h5"),
        "movie_frame_rate_hz": frame_rate,
        "output_json": str(output_dir / "output.json")
    }

    with open(input_dir / "input.json", "w") as j:
        json.dump(input_data, j, indent=2)
    copy_data_to_results(motion_corrected_fn.parent, output_dir)
