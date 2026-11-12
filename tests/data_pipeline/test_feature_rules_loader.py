import copy
import json
from pathlib import Path

import pytest

from data_transformation.feature_rules import FeatureRulesConfigError, load_feature_rules

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "feature_rules/feature-equivalence.example.json"


def _payload():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _load(tmp_path, payload):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return load_feature_rules(path)


def test_example_configuration_and_json_schema_are_valid_json():
    config = load_feature_rules(EXAMPLE)
    schema = json.loads(
        (ROOT / "feature_rules/feature-equivalence.schema.json").read_text(encoding="utf-8")
    )

    assert config.schema_version == 1
    assert len(config.rules) == 44
    numeric_defaults = {
        column.name: column.default
        for column in config.columns
        if column.value_type.value in {"integer", "decimal"}
    }
    assert numeric_defaults == {
        "usuarios_normales": 0,
        "usuarios_contador": 0,
        "usuarios_sin_clasificar": 0,
        "usuarios_app_movil": 0,
        "nomina_personas_max": 0,
    }
    assert schema["properties"]["schema_version"] == {"const": 1}


def test_loader_rejects_invalid_json_and_unsupported_version(tmp_path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(FeatureRulesConfigError, match="No se pudo leer"):
        load_feature_rules(invalid)

    payload = _payload()
    payload["schema_version"] = 2
    with pytest.raises(FeatureRulesConfigError, match="schema_version no soportada"):
        _load(tmp_path, payload)


def test_loader_rejects_unknown_keys_and_duplicate_rule_ids(tmp_path):
    payload = _payload()
    payload["unexpected"] = True
    with pytest.raises(FeatureRulesConfigError, match="claves desconocidas"):
        _load(tmp_path, payload)

    payload = _payload()
    duplicate = copy.deepcopy(payload["rule_sets"]["common"][0])
    payload["rule_sets"]["perseo"].append(duplicate)
    with pytest.raises(FeatureRulesConfigError, match="ID de regla duplicado"):
        _load(tmp_path, payload)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload["competitors"]["perseo"]["rule_sets"].append("missing"),
            "conjuntos inexistentes",
        ),
        (
            lambda payload: payload["rule_sets"]["common"][0]["outputs"][0].update(
                {"column": "missing"}
            ),
            "columna inexistente",
        ),
        (
            lambda payload: payload["columns"]["usuarios_normales"].update({"default": "cero"}),
            "debe ser integer",
        ),
        (
            lambda payload: payload["columns"]["usuarios_normales"].update({"reducer": "any"}),
            "no es compatible",
        ),
        (
            lambda payload: payload["rule_sets"]["common"][0]["when"].update({"pattern": "["}),
            "pattern inválido",
        ),
        (
            lambda payload: payload["rule_sets"]["common"][0]["outputs"][1]["value"].update(
                {"capture": "missing"}
            ),
            "captura inexistente",
        ),
        (
            lambda payload: payload["derived_columns"]["usuarios_totales"]["inputs"].append(
                "missing"
            ),
            "columnas inexistentes",
        ),
        (
            lambda payload: payload["columns"].update(
                {
                    "plan_id": {
                        "type": "string",
                        "default": None,
                        "reducer": "first",
                    }
                }
            ),
            "colisionan con group_by",
        ),
    ],
)
def test_loader_rejects_invalid_references_types_and_patterns(tmp_path, mutation, message):
    payload = _payload()
    mutation(payload)
    with pytest.raises(FeatureRulesConfigError, match=message):
        _load(tmp_path, payload)


def test_loader_rejects_derived_cycles(tmp_path):
    payload = _payload()
    payload["derived_columns"]["subtotal"] = {
        "type": "integer",
        "operation": "sum_columns",
        "inputs": ["usuarios_totales"],
        "null_policy": "null_if_all_null",
    }
    payload["derived_columns"]["usuarios_totales"]["inputs"] = ["subtotal"]

    with pytest.raises(FeatureRulesConfigError, match="ciclo"):
        _load(tmp_path, payload)


def test_loader_requires_exactly_one_output_source(tmp_path):
    payload = _payload()
    payload["rule_sets"]["common"][0]["outputs"][0]["value"] = {
        "literal": True,
        "field": "incluido",
    }

    with pytest.raises(FeatureRulesConfigError, match="exactamente"):
        _load(tmp_path, payload)
