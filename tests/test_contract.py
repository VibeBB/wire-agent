"""HarnessContract schema validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from helpers import example_contract_data
from wire.contract import HarnessContract


def test_example_contract_validates() -> None:
    contract = HarnessContract.model_validate(example_contract_data())
    assert contract.name == "sensor-harness"
    assert len(contract.wires) == 3
    assert contract.element_ids() == [
        "C1",
        "C2",
        "WT1",
        "WT2",
        "N1",
        "N2",
        "N3",
        "W1",
        "W2",
        "W3",
        "RT1",
        "RT2",
    ]


def test_unknown_wire_type_rejected() -> None:
    data = example_contract_data()
    data["wires"][0]["wire_type"] = "WT99"
    with pytest.raises(Exception, match="unknown wire type"):
        HarnessContract.model_validate(data)


def test_unknown_net_rejected() -> None:
    data = example_contract_data()
    data["wires"][1]["net"] = "N99"
    with pytest.raises(Exception, match="unknown net"):
        HarnessContract.model_validate(data)


def test_unknown_cavity_rejected() -> None:
    data = example_contract_data()
    data["wires"][0]["from_endpoint"]["cavity"] = "9"
    with pytest.raises(Exception, match="unknown cavity"):
        HarnessContract.model_validate(data)


def test_duplicate_ids_rejected() -> None:
    data = example_contract_data()
    data["nets"].append(dict(data["nets"][0]))
    with pytest.raises(Exception, match="must be unique"):
        HarnessContract.model_validate(data)


def test_derating_must_be_sorted() -> None:
    data = example_contract_data()
    points = data["wire_types"][0]["temp_derating"]
    points[0], points[1] = points[1], points[0]
    with pytest.raises(Exception, match="sorted"):
        HarnessContract.model_validate(data)


def test_extra_fields_rejected() -> None:
    data = example_contract_data()
    data["wires"][0]["mystery"] = 1
    with pytest.raises(ValidationError):
        HarnessContract.model_validate(data)


def test_splice_endpoint_validates() -> None:
    data = example_contract_data()
    data["splices"] = [{"id": "SP1"}]
    data["wires"][0]["to_endpoint"] = {"splice": "SP1"}
    leg = dict(data["wires"][0])
    leg["id"] = "W9"
    leg["from_endpoint"] = {"splice": "SP1"}
    leg["to_endpoint"] = {"connector": "C2", "cavity": "2"}
    data["wires"].append(leg)
    HarnessContract.model_validate(data)


def test_endpoint_rejects_connector_and_splice() -> None:
    data = example_contract_data()
    data["splices"] = [{"id": "SP1"}]
    data["wires"][0]["to_endpoint"] = {"connector": "C2", "cavity": "1", "splice": "SP1"}
    with pytest.raises(ValidationError):
        HarnessContract.model_validate(data)


def test_endpoint_rejects_bare_endpoint() -> None:
    data = example_contract_data()
    data["wires"][0]["to_endpoint"] = {"connector": "C2"}
    with pytest.raises(ValidationError):
        HarnessContract.model_validate(data)


def test_unknown_splice_rejected() -> None:
    data = example_contract_data()
    data["wires"][0]["to_endpoint"] = {"splice": "SP9"}
    with pytest.raises(ValidationError):
        HarnessContract.model_validate(data)


def test_duplicate_splice_id_rejected() -> None:
    data = example_contract_data()
    data["splices"] = [{"id": "SP1"}, {"id": "SP1"}]
    with pytest.raises(ValidationError):
        HarnessContract.model_validate(data)
