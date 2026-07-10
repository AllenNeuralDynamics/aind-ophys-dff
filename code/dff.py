import json
import logging
import os
from datetime import datetime as dt
from multiprocessing import Pool
from pathlib import Path

import aind_ophys_utils.dff as dff
import h5py
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from aind_data_schema.core.processing import DataProcess, ProcessName
from aind_data_schema.core.quality_control import (
    QCEvaluation,
    QCMetric,
    QCStatus,
    Stage,
    Status,
)
from aind_data_schema_models.modalities import Modality
from aind_log_utils.log import setup_logging
from aind_qcportal_schema.metric_value import CurationMetric
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
        description="Moving window size (in seconds) of the rolling percentile filter "
        "used to compute a rolling baseline",
    )
    short_window: float = Field(
        default=3.333,
        description="Moving window size (in seconds) of the median filter to compute the rolling "
        "median-filtered signal, which is subtracted from the input 'F' for noise_method=mad",
    )
    inactive_percentile: int = Field(
        default=10,
        description="Percentile value that defines the inactive frames used for calculating "
        "the baseline",
    )
    noise_method: str = Field(
        default="mad",
        description="Method for computing the noise, see ..signal_utils.noise_std "
        "Choices: 'mad', 'fft', 'welch'",
    )

    class Config:
        env_prefix = "DFF_"


def write_data_process(
    metadata: dict,
    input_fp: str | Path,
    output_fp: str | Path,
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


def make_output_directory(output_dir: Path, unique_id: str) -> str:
    """Creates the output directory if it does not exist

    Parameters
    ----------
    output_dir: Path
        output directory
    unique_id: str
        unique identifier

    Returns
    -------
    output_dir: str
        output directory
    """
    output_dir = output_dir / unique_id
    output_dir.mkdir(exist_ok=True)
    output_dir = output_dir / "dff"
    output_dir.mkdir(exist_ok=True)

    return output_dir


def get_frame_rate(session: dict) -> float:
    """Attempt to pull frame rate from session.json
    Raises ValueError if frame rate not in session.json

    Parameters
    ----------
    session: dict
        session metadata

    Returns
    -------
    frame_rate: float
        frame rate in Hz
    """
    frame_rate_hz = None
    for i in session.get("data_streams", ""):
        if i.get("ophys_fovs", ""):
            frame_rate_hz = i["ophys_fovs"][0]["frame_rate"]
            break
    if frame_rate_hz is None:
        raise ValueError("No frame rate found in session.json")
    if isinstance(frame_rate_hz, str):
        frame_rate_hz = float(frame_rate_hz)
    return frame_rate_hz


def plot_dff(
    trace: np.ndarray,
    baseline: np.ndarray,
    frame_rate: float,
    roi_id: int,
    fig_path: str | Path,
    unique_id: str,
    log: dict | None = None,
    zoom_duration: float = 60.0,
) -> None:
    """Thin wrapper around :func:`aind_ophys_utils.dff.plot_dff` that handles
    frame-rate-to-time conversion, triexp log annotation, and saving to disk."""
    t = np.arange(len(trace)) / frame_rate
    fig = dff.plot_dff(trace, baseline, t, zoom_duration=zoom_duration, roi_id=roi_id)
    title = f"cell_roi_id: {int(roi_id)}"
    if log is not None:
        title += (
            f"  (n_passes={log.get('n_passes')}, "
            f"winner={log.get('winner_combo')}, "
            f"trigger={log.get('pass1_trigger')})"
        )
    fig.axes[0].set_title(title)
    fig.savefig(
        Path(fig_path) / f"{unique_id}_{roi_id}_dff.png",
        dpi=200,
        bbox_inches="tight",
        pad_inches=0.02,
    )
    plt.close(fig)


def write_qc_evalutation(output_dir: Path, unique_id: str, N: int) -> None:
    """Writes QC metrics to json file.

    Parameters
    ----------
    output_dir: Path
        output directory
    unique_id: str
        unique identifier
    N: int
        number of ROIs detected
    """
    cell_plots = dict()
    for roi_id in range(N):
        cell_plots[str(roi_id)] = {
            "reference": f"{unique_id}/dff/plots/{unique_id}_{roi_id:0{len(str(N))}d}_dff.png"
        }
    curation = CurationMetric(curations=[json.dumps(cell_plots)])
    metric = QCMetric(
        name=f"{unique_id} dF/F",
        description="dF/F baseline correction",
        reference="",
        status_history=[
            QCStatus(evaluator="Automated", timestamp=dt.now(), status=Status.PASS)
        ],
        value=curation,
    )

    evaluation = QCEvaluation(
        modality=Modality.from_abbreviation("pophys"),
        stage=Stage.PROCESSING,
        name="dF/F",
        description="dF/F baseline correction for each ROI across all FOVs",
        allow_failed_metrics=False,
        metrics=[metric],
        tags=["dff"],
    )

    with open(output_dir / f"{unique_id}_dff_evaluation.json", "w") as f:
        json.dump(json.loads(evaluation.model_dump_json()), f, indent=4)


if __name__ == "__main__":
    start_time = dt.now()
    args = DFFSettings()
    input_dir = args.input_dir
    output_dir = args.output_dir
    data_description_data = get_metadata(input_dir, "data_description.json")
    name = data_description_data.get("name", "")
    subject_data = get_metadata(input_dir, "subject.json")
    subject_id = subject_data.get("subject_id", "")
    session_data = get_metadata(input_dir, "session.json")
    frame_rate = get_frame_rate(session_data)
    setup_logging("aind-ophys-dff", subject_id=subject_id, asset_name=name)
    extraction_dir = next(input_dir.rglob("*/extraction"))
    unique_id = extraction_dir.parent.name
    logging.info(f"Calculating dF/F for ExperimentID {unique_id}")
    extraction_fp = next(extraction_dir.glob("*extraction.h5"))
    output_dir = make_output_directory(output_dir, unique_id)
    with h5py.File(extraction_fp, "r") as f:
        traces = f["traces/corrected"][()]
    if len(traces):
        # Pass settings parameters to the dff function
        dff_traces, baseline, noise = dff.dff(
            traces,
            long_window=args.long_window,
            short_window=args.short_window,
            fs=frame_rate,
            inactive_percentile=args.inactive_percentile,
            noise_method=args.noise_method,
        )
    else:  # no ROIs detected
        dff_traces, baseline, noise = traces, traces, []
    skewness = skew(dff_traces, axis=1)
    with h5py.File(output_dir / f"{unique_id}_dff.h5", "w") as f:
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
        unique_id,
        start_time,
        dt.now(),
    )

    # QC plots
    N = traces.shape[0]
    if N:
        fig_path = output_dir / "plots"
        os.makedirs(fig_path, exist_ok=True)
        with Pool(int(tmp) if (tmp := os.environ.get("CO_CPUS")) else tmp) as pool:
            pool.starmap(
                plot_dff,
                zip(
                    traces,
                    np.maximum(baseline, noise[:, None]),
                    [frame_rate] * N,
                    [f"{n:0{len(str(N))}d}" for n in range(N)],
                    [fig_path] * N,
                    [unique_id] * N,
                ),
            )

    write_qc_evalutation(output_dir, unique_id, N)
