import argparse
import json
import logging
import os
from datetime import datetime as dt
from multiprocessing import Pool
from pathlib import Path
from typing import Union

import aind_ophys_utils.dff as dff
import h5py
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from aind_data_schema.core.processing import DataProcess, ProcessName
from aind_log_utils.log import setup_logging
from mpl_toolkits.axes_grid1.inset_locator import inset_axes, mark_inset
from numpy.typing import NDArray
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
    trace: NDArray,
    baseline: NDArray,
    dff_trace: NDArray,
    frame_rate: float,
    roi_id: int,
    fig_path: Union[str, Path],
    experiment_id: str,
    zoom_duration: float = 60.0,
) -> None:
    """Plot raw and dF/F traces with optional zoomed insets.

    Creates a multi-panel plot showing raw fluorescence signal and baseline-corrected
    dF/F trace. When zoom_duration is specified, includes three zoomed inset plots
    showing detailed views of the beginning, middle, and end of the recording session.

    Parameters
    ----------
    trace : NDArray
        Neuropil-corrected raw fluorescence trace
    baseline : NDArray
        Fitted baseline (F0) values
    dff_trace : NDArray
        Baseline-corrected dF/F trace (fractional units)
    frame_rate : float
        Frame rate in Hz
    roi_id : int
        Region of interest identifier for labeling the plot
    fig_path : str or Path
        Directory path where the output PNG file will be saved
    experiment_id: str
        experiment_id number
    zoom_duration : float, optional
        Duration in seconds for each zoomed inset window. If None or 0,
        creates a simpler 2-row layout without insets. If positive, creates
        a 3-row layout with inset zoom plots. Default is 60.0.

    Returns
    -------
    None
        Saves the plot as a PNG file to the specified path and closes the figure.

    Notes
    -----
    The function creates different layouts based on zoom_duration:

    - If zoom_duration is None or 0: 2 rows per channel (raw + dF/F)
    - If zoom_duration > 0: 3 rows per channel (raw + insets + dF/F)

    Inset windows show:
    - First: Beginning of recording (0 to zoom_duration seconds)
    - Middle: Center portion of recording
    - Last: End of recording (last zoom_duration seconds)

    The saved filename follows the pattern: '{experiment_id}_{roi_id}_dff.png'
    """
    t = np.arange(len(trace)) / frame_rate
    show_insets = zoom_duration is not None and zoom_duration > 0

    # Create figure and axes
    if show_insets:
        fig, ax = plt.subplots(3, 1, figsize=(12, 3.5))
    else:
        fig, ax = plt.subplots(2, 1, figsize=(12, 2), sharex=True)

    # Calculate row indices based on layout
    raw_idx = 0
    dff_idx = 2 if show_insets else 1
    inset_idx = 1 if show_insets else None

    # Plot raw signal
    ax[raw_idx].plot(t, trace, label=f"neuropil-corrected trace", c="C0")
    ax[raw_idx].plot(t, baseline, label=r"fitted F$_0$", c="#F0E442")
    ax[raw_idx].legend(
        loc=(0.692, 0.78), ncol=2, borderpad=0.05
    ).get_frame().set_linewidth(0.0)
    ax[raw_idx].set_ylabel("F [a.u.]")

    # Plot dF/F signal
    ax[dff_idx].plot(t, dff_trace * 100, label=f"$\\Delta$F/F", c="C2", zorder=-1)
    ax[dff_idx].axhline(0, c="k", ls="--")
    ax[dff_idx].legend(
        loc=(0.923, 0.78), ncol=1, borderpad=0.05
    ).get_frame().set_linewidth(0.0)
    ax[dff_idx].set_ylabel(r"$\Delta$F/F [%]", y=1 if show_insets else 0.5)

    # Add insets if requested
    if show_insets:
        t_total = t[-1] - t[0]
        zoom_windows = [
            (t[0], t[0] + zoom_duration),
            (
                t[0] + (t_total - zoom_duration) / 2,
                t[0] + (t_total + zoom_duration) / 2,
            ),
            (max(t[-1] - zoom_duration, t[0]), t[-1]),
        ]

        ax[inset_idx].axis("off")

        for j, (start_time, end_time) in enumerate(zoom_windows):
            inset_ax = inset_axes(
                ax[inset_idx],
                width="100%",
                height="100%",
                loc="center",
                bbox_to_anchor=([0.01, 0.34, 0.67][j], 0.0, 0.32, 0.8),
                bbox_transform=ax[inset_idx].transAxes,
            )

            mask = (t >= start_time) & (t <= end_time)
            if np.any(mask):
                t_zoom, dff_zoom = t[mask], dff_trace[mask] * 100

                inset_ax.plot(t_zoom, dff_zoom, c="C2", linewidth=1.5)
                inset_ax.axhline(0, c="k", ls="--")
                inset_ax.grid(True, alpha=0.8)
                inset_ax.set_xlim(start_time, end_time)

                if len(dff_zoom) > 0:
                    mi, ma = np.nanmin(dff_zoom), np.nanmax(dff_zoom)
                    y_margin = 0.1 * (ma - mi)
                    if ~np.isnan(y_margin):
                        inset_ax.set_ylim(mi - y_margin, ma + y_margin)

                inset_ax.set_title(
                    f"{['First', 'Middle', 'Last'][j]} {zoom_duration:.0f}s",
                    fontsize=10,
                    y=0.94,
                )
                inset_ax.set_xticks([])
                inset_ax.set_yticks([])

                mark_inset(
                    ax[dff_idx],
                    inset_ax,
                    loc1=1,
                    loc2=3,
                    fc="none",
                    ec="#333333",
                    alpha=0.8,
                    linestyle="--",
                    linewidth=1,
                )

    # Set x-limits and labels
    tmin, tmax = np.nanmin(t), np.nanmax(t)
    margin = (tmax - tmin) / 100
    ax[raw_idx].set_xlim(tmin - margin, tmax + margin)
    ax[dff_idx].set_xlim(tmin - margin, tmax + margin)
    plt.setp(ax[raw_idx].get_xticklabels(), visible=False)
    ax[dff_idx].set_xlabel("Time [s]")
    ax[0].set_title(f"cell_roi_id: {int(roi_id)}")
    plt.subplots_adjust(hspace=0.1, top=0.935, bottom=0.13, left=0.06, right=0.995)
    fig.savefig(
        fig_path / f"{experiment_id}_{roi_id}_dff.png",
        dpi=200,
        bbox_inches="tight",
        pad_inches=0.02,
    )
    plt.close(fig)


if __name__ == "__main__":
    start_time = dt.now()
    args = DFFSettings()
    input_dir = args.input_dir
    output_dir = args.output_dir
    data_description_data = get_metadata(input_dir, "data_description.json")
    name = data_description_data.get("name", "")
    subject_data = get_metadata(input_dir, "subject.json")
    subject_id = subject_data.get("subject_id", "")
    setup_logging("aind-ophys-dff", subject_id=subject_id, asset_name=name)
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

    # QC plots
    N = traces.shape[0]
    if N:
        session_data = get_metadata(input_dir, "session.json")
        frame_rate = get_frame_rate(session_data)
        fig_path = output_dir / "plots"
        os.makedirs(fig_path, exist_ok=True)
        with Pool(int(tmp) if (tmp := os.environ.get("CO_CPUS")) else tmp) as pool:
            pool.starmap(
                plot_dff,
                zip(
                    traces,
                    baseline,
                    dff_traces,
                    [frame_rate] * N,
                    [f"{n:0{len(str(N))}d}" for n in range(N)],
                    [fig_path] * N,
                    [experiment_id] * N,
                ),
            )
