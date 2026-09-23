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
