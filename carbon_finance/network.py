from __future__ import annotations

import numpy as np
import pandas as pd


def propagate_risk(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    decay: float = 0.55,
) -> tuple[pd.DataFrame, dict[str, list[dict[str, float | str]]]]:
    ids = nodes["company_id"].tolist()
    index = {node_id: i for i, node_id in enumerate(ids)}
    matrix = np.zeros((len(ids), len(ids)))
    for edge in edges.itertuples():
        if edge.source in index and edge.target in index:
            matrix[index[edge.target], index[edge.source]] += float(edge.weight)
    row_sums = matrix.sum(axis=1)
    matrix = matrix / np.maximum(row_sums[:, None], 1.0)

    initial = nodes["initial_risk"].to_numpy(dtype=float)
    first = decay * matrix @ initial
    second = decay**2 * matrix @ matrix @ initial
    total = np.clip(initial + first + second, 0, 1)
    result = nodes[["company_id", "company_name"]].copy()
    result["own_risk"] = initial
    result["first_order_risk"] = first
    result["second_order_risk"] = second
    result["network_risk"] = total

    paths: dict[str, list[dict[str, float | str]]] = {}
    edge_lookup = {(row.source, row.target): row for row in edges.itertuples()}
    for target in ids:
        candidates: list[dict[str, float | str]] = []
        for source in ids:
            edge = edge_lookup.get((source, target))
            if edge:
                contribution = decay * float(edge.weight) * initial[index[source]]
                candidates.append({"path": f"{source} -> {target}", "order": 1, "contribution": contribution})
            for middle in ids:
                first_edge = edge_lookup.get((source, middle))
                second_edge = edge_lookup.get((middle, target))
                if first_edge and second_edge and source != target:
                    contribution = decay**2 * float(first_edge.weight) * float(second_edge.weight) * initial[index[source]]
                    candidates.append({"path": f"{source} -> {middle} -> {target}", "order": 2, "contribution": contribution})
        paths[target] = sorted(candidates, key=lambda item: float(item["contribution"]), reverse=True)[:3]
    return result, paths
