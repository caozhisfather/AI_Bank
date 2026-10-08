import pandas as pd

from carbon_finance.network import propagate_risk


def test_two_order_propagation_follows_edge_direction():
    nodes = pd.DataFrame(
        [["A", "A企业", 0.5], ["B", "B企业", 0.1], ["C", "C企业", 0.1]],
        columns=["company_id", "company_name", "initial_risk"],
    )
    edges = pd.DataFrame(
        [["A", "B", 0.6], ["B", "C", 0.5]],
        columns=["source", "target", "weight"],
    )
    result, paths = propagate_risk(nodes, edges, decay=0.5)
    indexed = result.set_index("company_id")
    assert indexed.loc["B", "first_order_risk"] > 0
    assert indexed.loc["C", "second_order_risk"] > 0
    assert paths["C"][0]["path"] == "A -> B -> C"
