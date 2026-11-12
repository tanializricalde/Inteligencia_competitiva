import copy
import json
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from data_transformation.feature_rules import (
    FeatureRulesExecutionError,
    flatten_features,
    load_feature_rules,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "feature_rules/feature-equivalence.example.json"


def _load_payload(tmp_path, payload):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return load_feature_rules(path)


def _row(plan, competitor, name, included=1, category=None, **extra):
    return {
        "plan_id": plan,
        "competidor_id": competitor,
        "categoria_modulo": category,
        "nombre_modulo": name,
        "incluido": included,
        **extra,
    }


def test_domain_rules_extract_users_payroll_modules_and_dynamic_fallback():
    config = load_feature_rules(EXAMPLE)
    rows = [
        _row("s1", "siigo_ec", "2 usuarios | 1 usuario contador"),
        _row("s1", "siigo_ec", "2 usuarios | 1 usuario contador"),
        _row("s1", "siigo_ec", "2 usuarios contador"),
        _row("i1", "idrixcontable", "Usuarios: 2"),
        _row("i1", "idrixcontable", "Usuarios contador: 1"),
        _row("i1", "idrixcontable", "Nómina (5 personas)"),
        _row("p1", "perseo", "6 Usuarios"),
        _row("p1", "perseo", "1 Licencia App PerseoMóvil"),
        _row("p1", "perseo", "2 Licencias App PerseoMóvil"),
        _row("p2", "perseo", "Usuarios (4) / Aplicación móvil (1)"),
        _row("p2", "perseo", "Nómina de 15 personas*"),
        _row("p2", "perseo", "Nómina"),
        _row("p2", "perseo", "Facturación"),
        _row("p2", "perseo", "Conexión SRI y Registro Civil"),
        _row("p2", "perseo", "Centro de costos"),
        _row("p2", "perseo", "No configurado"),
    ]

    result = flatten_features(pd.DataFrame(rows), config=config)
    data = result.dataframe.set_index(["competidor_id", "plan_id"])

    assert data.loc[("siigo_ec", "s1"), "usuarios_normales"] == 2
    assert data.loc[("siigo_ec", "s1"), "usuarios_contador"] == 3
    assert data.loc[("siigo_ec", "s1"), "usuarios_totales"] == 5
    assert data.loc[("idrixcontable", "i1"), "usuarios_totales"] == 3
    assert data.loc[("idrixcontable", "i1"), "nomina_personas_max"] == 5
    assert data.loc[("perseo", "p1"), "usuarios_sin_clasificar"] == 6
    assert data.loc[("perseo", "p1"), "usuarios_app_movil"] == 3
    assert data.loc[("perseo", "p1"), "usuarios_totales"] == 9
    assert data.loc[("perseo", "p2"), "usuarios_totales"] == 5
    assert data.loc[("perseo", "p2"), "nomina_incluida"] == 1
    assert data.loc[("perseo", "p2"), "nomina_personas_max"] == 15
    assert data.loc[("perseo", "p2"), "centro_de_costos"] == 1
    assert data.loc[("perseo", "p2"), "total_modulos"] == 2
    assert (
        data.loc[("perseo", "p2"), "lista_modulos"]
        == "Facturación electrónica|Conexión SRI y Registro Civil"
    )
    assert data.loc[("perseo", "p2"), "no_configurado"] == 1
    assert data.loc[("siigo_ec", "s1"), "no_configurado"] == 0
    assert result.report.exact_duplicates_removed == 1
    assert result.report.match_counts["perseo_usuarios_y_app_movil"] == 1
    assert result.report.match_counts["centro_de_costos"] == 1
    assert "no_configurado" in result.report.dynamic_columns
    assert "centro_de_costos" not in result.report.dynamic_columns


def test_typed_feature_values_preserve_origin_availability_and_rebuild_wide_view():
    config = load_feature_rules(EXAMPLE)
    result = flatten_features(
        pd.DataFrame(
            [
                _row("pro", "siigo_ec", "2 usuarios | 1 usuario contador"),
                _row("pro", "siigo_ec", "No configurado", included=0),
            ]
        ),
        config=config,
        run_id="run-001",
    )
    values = result.values_dataframe.set_index("feature_code")

    assert values.loc["usuarios_normales", "value_integer"] == 2
    assert values.loc["usuarios_normales", "origin"] == "rule"
    assert values.loc["usuarios_normales", "rule_id"] == "siigo_usuarios_y_contador"
    assert values.loc["no_configurado", "value_boolean"] is False
    assert values.loc["no_configurado", "availability"] == "excluded"
    assert values.loc["no_configurado", "origin"] == "fallback"
    assert values.loc["nomina_personas_max", "value_integer"] == 0
    assert values.loc["nomina_personas_max", "availability"] == "unknown"
    assert values.loc["nomina_personas_max", "origin"] == "default"
    assert values.loc["usuarios_totales", "origin"] == "derived"
    assert bool(values.loc["usuarios_totales", "is_derived"]) is True
    assert set(result.values_dataframe["run_id"]) == {"run-001"}

    rebuilt = result.dataframe.set_index(["competidor_id", "plan_id"])
    assert rebuilt.loc[("siigo_ec", "pro"), "usuarios_normales"] == 2
    assert rebuilt.loc[("siigo_ec", "pro"), "no_configurado"] == 0


def test_payroll_without_quantity_does_not_increment_users():
    config = load_feature_rules(EXAMPLE)
    result = flatten_features(pd.DataFrame([_row("a", "anfibius", "Nómina")]), config=config)

    assert result.dataframe.loc[0, "nomina_incluida"] == 1
    assert result.dataframe.loc[0, "nomina_personas_max"] == 0
    assert result.dataframe.loc[0, "usuarios_totales"] == 0


def test_unknown_competitor_uses_dynamic_fallback_and_is_reported():
    config = load_feature_rules(EXAMPLE)
    result = flatten_features(
        pd.DataFrame([_row("x", "nuevo", "Característica libre")]), config=config
    )

    assert result.dataframe.loc[0, "caracteristica_libre"] == 1
    assert result.report.unknown_competitors == {"nuevo": 1}


def test_multiple_consuming_matches_are_fatal(tmp_path):
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    duplicate = copy.deepcopy(payload["rule_sets"]["common"][1])
    duplicate["id"] = "nomina_duplicada"
    payload["rule_sets"]["common"].append(duplicate)
    config = _load_payload(tmp_path, payload)

    with pytest.raises(FeatureRulesExecutionError, match="varias reglas") as caught:
        flatten_features(pd.DataFrame([_row("a", "anfibius", "Nómina")]), config=config)
    assert caught.value.feature_rules_report.multiple_matches[0]["rules"] == [
        "nomina_sin_limite",
        "nomina_duplicada",
    ]


def test_invalid_capture_can_be_reported_or_made_strict(tmp_path):
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    payload["behavior"]["invalid_capture"] = "report"
    payload["rule_sets"]["idrixcontable"][0]["when"]["pattern"] = (
        "^\\s*usuarios?\\s*:\\s*(?P<cantidad>.+)\\s*$"
    )
    config = _load_payload(tmp_path, payload)
    frame = pd.DataFrame([_row("i", "idrixcontable", "Usuarios: varios")])

    result = flatten_features(frame, config=config)
    assert result.dataframe.loc[0, "usuarios_normales"] == 0
    assert result.report.invalid_captures[0]["rule"] == "idrix_usuarios_normales"
    with pytest.raises(FeatureRulesExecutionError, match="Captura inválida"):
        flatten_features(frame, config=config, strict=True)


def test_priority_and_first_policy_choose_the_highest_consuming_rule(tmp_path):
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    payload["behavior"]["multiple_matching_rules"] = "first"
    higher = copy.deepcopy(payload["rule_sets"]["common"][1])
    higher["id"] = "nomina_prioritaria"
    higher["priority"] = 500
    higher["outputs"][0]["value"] = {"literal": False}
    payload["rule_sets"]["common"].append(higher)
    config = _load_payload(tmp_path, payload)

    result = flatten_features(pd.DataFrame([_row("a", "anfibius", "Nómina")]), config=config)

    assert result.dataframe.loc[0, "nomina_incluida"] == 0
    assert result.report.match_counts["nomina_prioritaria"] == 1
    assert result.report.match_counts["nomina_sin_limite"] == 0
    assert result.report.multiple_matches


def test_error_reducer_fails_on_distinct_contributions(tmp_path):
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    payload["columns"]["nomina_personas_max"]["reducer"] = "error"
    config = _load_payload(tmp_path, payload)
    frame = pd.DataFrame(
        [
            _row("a", "anfibius", "Nómina (5 personas)"),
            _row("a", "anfibius", "Nómina de 15 personas*"),
        ]
    )

    with pytest.raises(FeatureRulesExecutionError, match="más de un valor"):
        flatten_features(frame, config=config)


def test_explicit_zero_participates_in_derived_sum():
    config = load_feature_rules(EXAMPLE)
    result = flatten_features(pd.DataFrame([_row("p", "perseo", "Usuarios app: 0")]), config=config)

    assert result.dataframe.loc[0, "usuarios_app_movil"] == 0
    assert result.dataframe.loc[0, "usuarios_totales"] == 0


@pytest.mark.parametrize("mode", ["ignore", "error"])
def test_unmatched_mode_can_ignore_or_fail(tmp_path, mode):
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    payload["behavior"]["unmatched"]["mode"] = mode
    config = _load_payload(tmp_path, payload)
    frame = pd.DataFrame([_row("a", "anfibius", "Libre")])

    if mode == "error":
        with pytest.raises(FeatureRulesExecutionError, match="sin regla"):
            flatten_features(frame, config=config)
    else:
        result = flatten_features(frame, config=config)
        assert "libre" not in result.dataframe
        assert result.report.unmatched_features["libre"] == 1


def test_dynamic_column_collision_is_never_silent():
    config = load_feature_rules(EXAMPLE)

    with pytest.raises(FeatureRulesExecutionError, match="colisiona"):
        flatten_features(pd.DataFrame([_row("a", "anfibius", "Usuarios normales")]), config=config)


def test_reducers_are_typed_stable_and_deduplicate_exact_rows(tmp_path):
    payload = {
        "schema_version": 1,
        "input": {
            "group_by": ["competidor_id", "plan_id"],
            "competitor_field": "competidor_id",
            "text_field": "nombre_modulo",
            "normalized_text_field": "nombre_modulo_normalizado",
            "included_field": "incluido",
            "deduplicate_by": [
                "competidor_id",
                "plan_id",
                "nombre_modulo_normalizado",
                "incluido",
                "categoria_modulo",
            ],
        },
        "behavior": {
            "unknown_competitor": "error",
            "multiple_matching_rules": "error",
            "invalid_capture": "error",
            "unmatched": {
                "mode": "error",
                "column_from": "nombre_modulo_normalizado",
                "value_from": "incluido",
                "reducer": "any",
                "default": False,
                "prefix": "",
            },
        },
        "columns": {
            "sum_value": {"type": "integer", "default": None, "reducer": "sum"},
            "max_value": {"type": "integer", "default": None, "reducer": "max"},
            "min_value": {"type": "integer", "default": None, "reducer": "min"},
            "first_value": {"type": "string", "default": None, "reducer": "first"},
            "last_value": {"type": "string", "default": None, "reducer": "last"},
            "any_value": {"type": "boolean", "default": False, "reducer": "any"},
            "all_value": {"type": "boolean", "default": False, "reducer": "all"},
            "joined_value": {
                "type": "string_list",
                "default": None,
                "reducer": "join_unique",
            },
            "error_value": {"type": "string", "default": None, "reducer": "error"},
        },
        "derived_columns": {},
        "rule_sets": {
            "common": [
                {
                    "id": "collect",
                    "priority": 1,
                    "when": {
                        "field": "nombre_modulo_normalizado",
                        "operator": "equals",
                        "value": "match",
                    },
                    "outputs": [
                        {"column": "sum_value", "value": {"field": "number"}},
                        {"column": "max_value", "value": {"field": "number"}},
                        {"column": "min_value", "value": {"field": "number"}},
                        {"column": "first_value", "value": {"field": "text"}},
                        {"column": "last_value", "value": {"field": "text"}},
                        {"column": "any_value", "value": {"field": "flag"}},
                        {"column": "all_value", "value": {"field": "flag"}},
                        {"column": "joined_value", "value": {"field": "text"}},
                        {"column": "error_value", "value": {"literal": "same"}},
                    ],
                    "consume": True,
                }
            ]
        },
        "competitors": {"comp": {"rule_sets": ["common"]}},
    }
    config = _load_payload(tmp_path, payload)
    rows = [
        _row("p", "comp", "match", category="one", number=1, text="a", flag=True),
        _row("p", "comp", "match", category="two", number=2, text="b", flag=False),
        _row("p", "comp", "match", category="two", number=2, text="b", flag=False),
    ]

    result = flatten_features(pd.DataFrame(rows), config=config)
    row = result.dataframe.iloc[0]
    assert row["sum_value"] == 3
    assert row["max_value"] == 2
    assert row["min_value"] == 1
    assert row["first_value"] == "a"
    assert row["last_value"] == "b"
    assert row["any_value"] == 1
    assert row["all_value"] == 0
    assert row["joined_value"] == ["a", "b"]
    assert row["error_value"] == "same"
    assert result.report.exact_duplicates_removed == 1


def test_same_input_and_configuration_are_deterministic():
    config = load_feature_rules(EXAMPLE)
    frame = pd.DataFrame(
        [
            _row("p", "perseo", "No configurado"),
            _row("p", "perseo", "Usuarios: 3"),
        ]
    )

    first = flatten_features(frame, config=config)
    second = flatten_features(frame, config=config)

    assert_frame_equal(first.dataframe, second.dataframe)
    assert first.report.as_dict() == second.report.as_dict()
