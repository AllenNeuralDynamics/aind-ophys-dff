import os
import re
import argparse
import json
from pathlib import Path

def make_output_directory(output_dir: str, h5_file: str, plane: str=None) -> str:
    """Creates the output directory if it does not exist
    
    Parameters
    ----------
    output_dir: str
        output directory
    h5_file: str 
        h5 file path
    plane: str
        plane number
    
    Returns
    -------
    output_dir: str
        output directory
    """
    exp_to_match = r"Other_\d{6}_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}"
    try:
        parent_dir = re.findall(exp_to_match, h5_file)[0] + "_processed_" + now()
    except IndexError:
        return output_dir
    if plane:
        output_dir = os.path.join(output_dir, parent_dir, plane)
    else:
        output_dir = os.path.join(output_dir, parent_dir)
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def find_h5_file(file_name: str) -> str:
    """Finds the h5 file path

    Args:
        file_name (str): file name

    Returns:
        str: h5 file path
    """
    name = f"{file_name}.h5"
    path = "/data/"
    for root, dirs, files in os.walk(path):
        for f in files:
            if name in f:
                return os.path.join(root, f)
            
if __name__ == "__main__":
    # Generate input json
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input-filename", type=str, help="Neuropil tracefile path")
    parser.add_argument("-o", "--output-dir", type=str, help="Output directory", default="/results/")
    parser.add_argument("-a", "--action", type=str, help="action to perform")
    
    args = parser.parse_args()
    neuropil_trace_h5 = args.input_filename
    if not neuropil_trace_h5:
        neuropil_trace_h5 = find_h5_file("neuropil_traces")
    # if not plane:
    plane = os.path.dirname(neuropil_trace_h5).split("/")[-1]
    if not plane.isdigit():
        plane = None
    abs_output = str(Path(args.output_dir).absolute())
    output_dir = make_output_directory(abs_output, neuropil_trace_h5, plane)
    parent_dir = os.path.dirname(neuropil_trace_h5)
    process_json = os.path.join(parent_dir, "processing.json")
    with open(process_json, "r") as j:
        data = json.load(j)
    frame_rate = data["data_processes"][0]["parameters"]["movie_frame_rate_hz"]
    input_data = {
        "input_file": neuropil_trace_h5,
        "output_file": os.path.join(output_dir, "dff.h5"),
        "movie_frame_rate_hz": frame_rate,
    }

    try:
        with open("/data/input.json", "w") as j:
            json.dump(input_data, j, indent=2)
    except Exception as e:
        raise Exception(f"Error writing json file: {e}")
