import json
import logging
import os
from datetime import datetime as dt
from multiprocessing import Pool
from pathlib import Path
from typing import Literal

import h5py
from aind_ophys_utils import dff as dff_percentile
from aind_ophys_dff_library.dff_config import set_dff_config
from aind_ophys_dff_library.triexp_dff import dff as triexp_dff, log_to_jsonable
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
    """Settings for dF/F calculation."""

    input_dir: Path = Field(
        default="/data",
        description="Input directory containing extraction.h5 and metadata files",
    )
    output_dir: Path = Field(
        default="/results",
        description="Output directory where results are saved",
    )
    method: Literal["triexp", "percentile"] = Field(
        default="triexp",
        description=(
            "dF/F algorithm: 'triexp' (parametric 3-pass triexponential baseline fit) or "
            "'percentile' (rolling-percentile baseline)."
        ),
    )

    # Percentile parameters — read only when method == 'percentile'.
    long_window: float = Field(
        default=60.0,
        description="Percentile baseline window (s). Used only when method='percentile'.",
    )
    short_window: float = Field(
        default=3.333,
        description="Short detrending window (s). Used only when method='percentile'.",
    )
    inactive_percentile: int = Field(
        default=10,
        description="Inactive percentile for F0. Used only when method='percentile'.",
    )
    noise_method: str = Field(
        default="mad",
        description="Noise estimator ('mad'|'fft'|'welch'). Used only when method='percentile'.",
    )

    # Triexp parameters — read only when method == 'triexp'.
    sigma_anneal_steps: int = Field(
        default=1,
        description=(
            "IRLS sigma-annealing steps (aind_ophys_utils.baseline_fitting."
            "nonlinear_fit). 1 (default) or 2 disable annealing "
            "(single-jump); 3 enables one intermediate step; 4 uses two; "
            "higher graduates further but exceeds the internal maxiter=5. "
            "Used only when method='triexp'."
        ),
    )
    triexp_config_overrides: str = Field(
        default="{}",
        description=(
            "JSON object of overrides for set_dff_config. Keys must be a subset of "
            "set_dff_config's keyword arguments (except sigma_anneal_steps, which "
            "has its own dedicated field above); any key omitted falls back to the "
            "function's default. Used only when method='triexp'."
        ),
    )

    class Config:
        env_prefix = "DFF_"


def _jsonify_log(roi_idx: int, log: dict) -> dict:
    """Wrap library.log_to_jsonable with this capsule's per-ROI identity prefix."""
    return {"roi": roi_idx, **log_to_jsonable(log)}


def _parse_triexp_overrides(raw: str) -> dict:
    """Parse and validate the --triexp-config-overrides JSON string.

    Returns a dict of validated overrides to splat into ``set_dff_config``.
    Fails fast on invalid JSON, non-object root, or unknown keys.
    """
    import inspect

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"triexp_config_overrides is not valid JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise ValueError(
            f"triexp_config_overrides must be a JSON object, got {type(parsed).__name__}"
        )
    # Exclude positional args + fields exposed as dedicated DFFSettings knobs
    # (dedicated fields are authoritative; JSON blob must not shadow them).
    allowed = set(inspect.signature(set_dff_config).parameters) - {
        "F", "fs", "ts", "sigma_anneal_steps",
    }
    unknown = set(parsed) - allowed
    if unknown:
        raise ValueError(
            f"triexp_config_overrides contains unknown keys: {sorted(unknown)}. "
            f"Allowed: {sorted(allowed)}"
        )
    return parsed


def compute_dff(
    traces: np.ndarray,
    settings: "DFFSettings",
    frame_rate: float,
    ts: Optional[np.ndarray],
    n_jobs: int,
) -> tuple:
    """Dispatch to the selected dF/F algorithm; return a uniform 5-tuple.

    Parameters
    ----------
    traces : (N, T) ndarray
        Neuropil-corrected fluorescence traces.
    settings : DFFSettings
        Parsed capsule settings; ``settings.method`` selects the algorithm.
    frame_rate : float
        Sampling frequency (Hz).
    ts : (T,) ndarray or None
        Per-frame timestamps (s). Used only by triexp; ignored by percentile.
    n_jobs : int
        Worker count. ``-1`` uses all CPUs (joblib semantics). The percentile
        path translates ``<= 0`` to ``None`` for ``multiprocessing.Pool``.

    Returns
    -------
    dff_traces : (N, T) ndarray
    baseline : (N, T) ndarray
    noise : (N,) ndarray or scalar
    logs : list[dict] (triexp) or None (percentile)
    config_snapshot : dict (triexp) or None (percentile)
    """
    if settings.method == "triexp":
        overrides = _parse_triexp_overrides(settings.triexp_config_overrides)
        config = set_dff_config(
            traces, fs=frame_rate, ts=ts,
            sigma_anneal_steps=settings.sigma_anneal_steps,
            **overrides,
        )
        dff_traces, baseline, noise, _params, logs = triexp_dff(
            traces, config, n_jobs=n_jobs,
        )
        return dff_traces, baseline, noise, logs, config.params

    percentile_n_jobs = n_jobs if n_jobs and n_jobs > 0 else None
    dff_traces, baseline, noise = dff_percentile.dff(
        traces,
        long_window=settings.long_window,
        short_window=settings.short_window,
        fs=frame_rate,
        inactive_percentile=settings.inactive_percentile,
        noise_method=settings.noise_method,
        n_jobs=percentile_n_jobs,
    )
    return dff_traces, baseline, noise, None, None


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
    fig = dff_percentile.plot_dff(trace, baseline, t, zoom_duration=zoom_duration, roi_id=roi_id)
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
        n_jobs = int(os.environ.get("CO_CPUS") or -1)
        dff_traces, baseline, noise, logs, config_snapshot = compute_dff(
            traces, args, frame_rate, None, n_jobs,
        )
    else:  # no ROIs detected
        dff_traces, baseline, noise = traces, traces, np.asarray([])
        logs, config_snapshot = None, None

    skewness = skew(dff_traces, axis=1)
    with h5py.File(output_dir / f"{unique_id}_dff.h5", "w") as f:
        f.create_dataset("data", data=dff_traces)
        f.create_dataset("baseline", data=baseline)
        f.create_dataset("noise", data=noise)
        f.create_dataset("skewness", data=skewness)

    logs_json = (
        [_jsonify_log(i, lg) for i, lg in enumerate(logs)] if logs is not None else []
    )
    with open(output_dir / f"{unique_id}_dff_logs.json", "w") as f:
        json.dump(logs_json, f, indent=2)

    # Include settings + triexp config snapshot in metadata
    input_params = {**vars(args), "triexp_config": config_snapshot}
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
        plot_logs = logs if logs is not None else [None] * N
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
                    plot_logs,
                ),
            )

    write_qc_evalutation(output_dir, unique_id, N)
