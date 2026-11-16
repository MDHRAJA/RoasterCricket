"""Data-only JSON inference for the research winner challenger; no pickle loading."""

import json
from pathlib import Path

import numpy as np
from scipy.special import expit

MODEL_SCHEMA = "ipl-post-toss-winner-json-v1"


def calibrate(probabilities, parameters):
    p = np.clip(np.asarray(probabilities, dtype=float), 1e-8, 1 - 1e-8)
    return expit(parameters["intercept"] + parameters["slope"] * np.log(p / (1 - p)))


def _tree_predict(x, tree):
    output = np.empty(len(x))
    for row_index, row in enumerate(x):
        node = 0
        steps = 0
        while tree["left"][node] >= 0:
            feature = tree["feature"][node]
            node = (
                tree["left"][node]
                if float(row[feature]) <= tree["threshold"][node]
                else tree["right"][node]
            )
            steps += 1
            if steps > len(tree["left"]):
                raise ValueError("Cyclic or malformed model tree")
        output[row_index] = tree["value"][node]
    return output


def predict_component(x_all, component):
    x = np.asarray(x_all, dtype=float)[:, component["columns"]]
    if not np.all(np.isfinite(x)):
        raise ValueError("Non-finite winner-model inputs")
    kind = component["family"]
    if kind == "logistic":
        z = ((x - component["center"]) / component["scale"]) @ component["weights"] + component[
            "intercept"
        ]
        return expit(z)
    if kind == "forest":
        x = x.astype(np.float32)
        return np.mean([_tree_predict(x, tree) for tree in component["trees"]], axis=0)
    if kind in ("gradient", "histogram"):
        if kind == "gradient":
            x = x.astype(np.float32)
        raw = np.full(len(x), component["initial_logit"], dtype=float)
        for tree in component["trees"]:
            raw += component["learning_rate"] * _tree_predict(x, tree)
        return expit(raw)
    raise ValueError("Unsupported JSON model family")


def predict_json_model(x, model):
    if model["schema"] != MODEL_SCHEMA:
        raise ValueError("Unsupported winner model schema")
    values = np.asarray(x, dtype=float)
    if values.ndim != 2 or values.shape[1] != len(model["feature_names"]):
        raise ValueError("Winner feature schema mismatch")
    if model["components"]:
        raw = np.mean([predict_component(values, c) for c in model["components"]], axis=0)
    elif model.get("baseline_feature"):
        raw = values[:, model["feature_names"].index(model["baseline_feature"])]
    else:
        raw = np.full(len(values), model["constant_probability"])
    return calibrate(raw, model.get("calibration", {"intercept": 0.0, "slope": 1.0}))


def load_json_model(path):
    path = Path(path)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Winner model artifact is too large")
    model = json.loads(path.read_text("utf-8"))
    if model.get("schema") != MODEL_SCHEMA or not isinstance(model.get("feature_names"), list):
        raise ValueError("Invalid winner model artifact")
    # Validate numerical structure before any request enters the predictor.
    names = model["feature_names"]
    if not names or len(names) > 256 or len(names) != len(set(names)):
        raise ValueError("Invalid winner feature names")
    for component in model.get("components", []):
        columns = component["columns"]
        if not columns or any(not isinstance(k, int) or not 0 <= k < len(names) for k in columns):
            raise ValueError("Invalid winner feature mapping")
        for tree in component.get("trees", []):
            n = len(tree["left"])
            if not 1 <= n <= 10000 or any(
                len(tree[k]) != n for k in ("right", "feature", "threshold", "value")
            ):
                raise ValueError("Invalid winner tree shape")
            for i in range(n):
                if tree["left"][i] >= 0 and (
                    not 0 <= tree["feature"][i] < len(columns)
                    or not 0 <= tree["left"][i] < n
                    or not 0 <= tree["right"][i] < n
                ):
                    raise ValueError("Invalid winner tree branch")
    probe = predict_json_model(np.zeros((1, len(names))), model)
    if not np.all(np.isfinite(probe)) or np.any(probe < 0) or np.any(probe > 1):
        raise ValueError("Invalid winner probabilities")
    return model
