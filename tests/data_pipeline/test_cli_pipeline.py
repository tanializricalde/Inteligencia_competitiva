import copy
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from data_cleaning.__main__ import main as cleaning_main
from data_transformation.__main__ import main as transformation_main
from scraper_cli.exporters import export_rows
from scraper_cli.schemas import PLAN_FEATURE_FIELDS, PLAN_FIELDS, REVIEW_FIELDS

ROOT = Path(__file__).resolve().parents[2]
FEATURE_RULES = ROOT / "feature_rules/feature-equivalence.example.json"


def _review_row():
    return {
        "review_id": "r-001",
        "competidor_id": "comp",
        "app_id": None,
        "plataforma": "google_maps",
        "pais_codigo": "EC",
        "fecha_comentario": "2026-01-01T00:00:00Z",
        "usuario_nombre": "  Ana  ",
        "calificacion_estrellas": 5,
        "comentario_cliente": " Muy\n bien ",
        "version_app": None,
        "likes_comentario": 0,
        "categoria_tema": None,
        "sentimiento": None,
        "tiene_respuesta": False,
        "fecha_respuesta": None,
        "respuesta_desarrollador": None,
        "dias_para_responder": None,
        "timestamp_ingesta": datetime(2026, 1, 2, tzinfo=UTC).isoformat(),
    }


def _plan_row():
    return {
        "timestamp_utc": "2026-01-01T00:00:00Z",
        "competidor_id": "comp",
        "competidor_nombre": "Competidor",
        "plan_id": "basic",
        "plan_nombre": "Básico",
        "producto": "Contabilidad",
        "moneda": "USD",
        "precio_mensual": 10,
        "precio_anual_total": None,
        "precio_mensual_efectivo": None,
        "descuento_anual_pct": None,
        "es_oferta_activa": False,
        "promocion_texto": None,
        "url_fuente": "https://example.test/plans",
    }


def _feature_row():
    return {
        "plan_id": "basic",
        "competidor_id": "comp",
        "categoria_modulo": "Ventas",
        "nombre_modulo": "Facturación",
        "incluido": True,
        "costo_adicional": None,
    }


def test_scraper_csv_can_flow_through_both_clis_without_manual_edits(tmp_path):
    raw = tmp_path / "raw" / "reviews.csv"
    clean = tmp_path / "clean" / "reviews.csv"
    normalized = tmp_path / "normalized" / "reviews.csv"
    raw.parent.mkdir()
    export_rows([_review_row()], REVIEW_FIELDS, output_format="csv", output=raw)

    assert cleaning_main([str(raw), "--output", str(clean)]) == 0
    assert transformation_main([str(clean), "--output", str(normalized)]) == 0

    with normalized.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["review_id"] == "r-001"
    assert rows[0]["usuario_nombre"] == "Ana"
    assert rows[0]["comentario_cliente"] == "Muy bien"
    assert rows[0]["sentimiento_por_calificacion"] == "positive"
    assert rows[0]["tiene_respuesta"] == "0"


def test_json_input_output_explicit_type_and_auto_override(tmp_path):
    source = tmp_path / "misleading-plans.json"
    output = tmp_path / "clean.json"
    normalized = tmp_path / "normalized" / "reviews.json"
    source.write_text(
        json.dumps([_review_row()], ensure_ascii=False, default=str), encoding="utf-8"
    )

    assert (
        cleaning_main(
            [str(source), "--type", "review", "--output", str(output), "--format", "json"]
        )
        == 0
    )
    assert json.loads(output.read_text(encoding="utf-8"))[0]["review_id"] == "r-001"
    assert transformation_main([str(output), "--output", str(normalized)]) == 0
    payload = json.loads(normalized.read_text(encoding="utf-8"))
    assert payload[0]["calificacion_estrellas"] == 5
    assert payload[0]["tiene_respuesta"] == 0


def test_cli_rejects_overwrite_input_and_existing_output(tmp_path):
    source = tmp_path / "reviews.csv"
    target = tmp_path / "clean.csv"
    export_rows([_review_row()], REVIEW_FIELDS, output_format="csv", output=source)
    target.write_text("original", encoding="utf-8")

    assert cleaning_main([str(source), "--output", str(target)]) == 5
    assert target.read_text(encoding="utf-8") == "original"
    assert cleaning_main([str(source), "--output", str(source), "--overwrite"]) == 5


def test_cli_returns_detection_error_for_unknown_data(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("foo\nbar\n", encoding="utf-8")

    assert cleaning_main([str(source), "--output", str(tmp_path / "out.csv")]) == 2


def test_cleaning_consolidates_multiple_review_files_and_deduplicates(tmp_path):
    first = tmp_path / "reviews-a.csv"
    second = tmp_path / "reviews-b.csv"
    output = tmp_path / "clean" / "all-reviews.csv"
    row = _review_row()
    export_rows([row], REVIEW_FIELDS, output_format="csv", output=first)
    export_rows([row], REVIEW_FIELDS, output_format="csv", output=second)

    assert (
        cleaning_main([str(first), str(second), "--type", "review", "--output", str(output)]) == 0
    )
    with output.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["review_id"] == "r-001"


def test_batch_auto_groups_directory_and_accepts_custom_names(tmp_path):
    source = tmp_path / "raw"
    nested = source / "nested"
    nested.mkdir(parents=True)
    export_rows([_review_row()], REVIEW_FIELDS, output_format="csv", output=source / "reviews.csv")
    (nested / "plans.json").write_text(
        json.dumps(
            [
                {
                    "timestamp_utc": "2026-01-01T00:00:00Z",
                    "competidor_id": "comp",
                    "plan_id": "basic",
                    "plan_nombre": "Básico",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (nested / "features.csv").write_text(
        "plan_id,competidor_id,nombre_modulo,incluido\nbasic,comp,Facturación,true\n",
        encoding="utf-8",
    )
    (source / "notes.txt").write_text("se ignora", encoding="utf-8")
    output = tmp_path / "clean"

    assert (
        cleaning_main(
            [
                str(source),
                "--output-dir",
                str(output),
                "--review-filename",
                "opiniones.json",
                "--plan-filename",
                "catalogo",
            ]
        )
        == 0
    )
    assert (output / "opiniones.json").is_file()
    assert (output / "catalogo.csv").is_file()
    assert (output / "features.csv").is_file()


def test_batch_explicit_type_filters_other_deducible_types(tmp_path):
    source = tmp_path / "raw"
    source.mkdir()
    export_rows([_review_row()], REVIEW_FIELDS, output_format="csv", output=source / "reviews.csv")
    (source / "plans.csv").write_text(
        "plan_id,plan_nombre,competidor_id,timestamp_utc\nbasic,Básico,comp,2026-01-01T00:00:00Z\n",
        encoding="utf-8",
    )
    output = tmp_path / "normalized" / "reviews.json"

    assert transformation_main([str(source), "--type", "review", "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert [row["review_id"] for row in payload] == ["r-001"]


def test_transformation_batch_writes_one_canonical_file_per_type(tmp_path):
    source = tmp_path / "clean"
    source.mkdir()
    export_rows([_review_row()], REVIEW_FIELDS, output_format="csv", output=source / "reviews.csv")
    export_rows([_plan_row()], PLAN_FIELDS, output_format="csv", output=source / "plans.csv")
    export_rows(
        [_feature_row()],
        PLAN_FEATURE_FIELDS,
        output_format="csv",
        output=source / "features.csv",
    )
    output = tmp_path / "normalized"

    assert transformation_main([str(source), "--output-dir", str(output)]) == 0
    assert (output / "reviews.csv").is_file()
    assert (output / "plans.csv").is_file()
    assert (output / "features.csv").is_file()


def test_batch_skips_unknown_file_with_warning_and_strict_rejects_it(tmp_path):
    source = tmp_path / "raw"
    source.mkdir()
    export_rows([_review_row()], REVIEW_FIELDS, output_format="csv", output=source / "reviews.csv")
    (source / "unknown.csv").write_text("foo\nbar\n", encoding="utf-8")

    output = tmp_path / "clean"
    assert cleaning_main([str(source), "--output-dir", str(output)]) == 4
    assert (output / "reviews.csv").is_file()

    strict_output = tmp_path / "strict"
    assert cleaning_main([str(source), "--output-dir", str(strict_output), "--strict"]) == 2
    assert not strict_output.exists()


def test_batch_validates_output_contract_before_writing(tmp_path):
    source = tmp_path / "raw"
    source.mkdir()
    export_rows([_review_row()], REVIEW_FIELDS, output_format="csv", output=source / "reviews.csv")
    (source / "plans.csv").write_text(
        "plan_id,plan_nombre,competidor_id,timestamp_utc\nbasic,Básico,comp,2026-01-01T00:00:00Z\n",
        encoding="utf-8",
    )
    output = tmp_path / "clean"
    output.mkdir()
    existing = output / "plans.csv"
    existing.write_text("original", encoding="utf-8")

    assert cleaning_main([str(source), "--output-dir", str(output)]) == 5
    assert existing.read_text(encoding="utf-8") == "original"
    assert not (output / "reviews.csv").exists()


def test_multiple_auto_inputs_require_output_directory(tmp_path):
    first = tmp_path / "reviews-a.csv"
    second = tmp_path / "reviews-b.csv"
    export_rows([_review_row()], REVIEW_FIELDS, output_format="csv", output=first)
    export_rows([_review_row()], REVIEW_FIELDS, output_format="csv", output=second)

    assert cleaning_main([str(first), str(second), "--output", str(tmp_path / "out.csv")]) == 2


def test_batch_rejects_output_name_with_path_components(tmp_path):
    source = tmp_path / "raw"
    source.mkdir()
    export_rows([_review_row()], REVIEW_FIELDS, output_format="csv", output=source / "reviews.csv")

    assert (
        cleaning_main(
            [
                str(source),
                "--output-dir",
                str(tmp_path / "clean"),
                "--review-filename",
                "nested/reviews.csv",
            ]
        )
        == 2
    )


def test_batch_rejects_output_that_is_also_an_input(tmp_path):
    source = tmp_path / "raw"
    source.mkdir()
    reviews = source / "reviews.csv"
    export_rows([_review_row()], REVIEW_FIELDS, output_format="csv", output=reviews)

    assert cleaning_main([str(source), "--output-dir", str(source), "--overwrite"]) == 5
    with reviews.open(encoding="utf-8", newline="") as stream:
        assert list(csv.DictReader(stream))[0]["review_id"] == "r-001"


def test_cli_writes_quality_report_and_feature_wide_view(tmp_path):
    source = tmp_path / "features.csv"
    clean = tmp_path / "clean.csv"
    normalized = tmp_path / "normalized.csv"
    report = tmp_path / "report.json"
    wide = tmp_path / "wide.json"
    export_rows([_feature_row()], PLAN_FEATURE_FIELDS, output_format="csv", output=source)

    assert (
        cleaning_main(
            [str(source), "--output", str(clean), "--report", str(tmp_path / "clean-report.json")]
        )
        == 0
    )
    assert (
        transformation_main(
            [
                str(clean),
                "--output",
                str(normalized),
                "--report",
                str(report),
                "--wide-output",
                str(wide),
            ]
        )
        == 0
    )
    assert json.loads(report.read_text(encoding="utf-8"))[0]["rules_version"]
    assert json.loads(wide.read_text(encoding="utf-8"))[0]["facturacion"] == 1


def test_cli_applies_feature_rules_and_writes_coverage_report(tmp_path):
    source = tmp_path / "features.csv"
    normalized = tmp_path / "normalized.csv"
    wide = tmp_path / "wide.json"
    values = tmp_path / "feature-values.json"
    rules_report = tmp_path / "feature-rules-report.json"
    rows = [
        {
            **_feature_row(),
            "plan_id": "pro",
            "competidor_id": "siigo_ec",
            "nombre_modulo": "2 usuarios | 1 usuario contador",
        },
        {
            **_feature_row(),
            "plan_id": "pro",
            "competidor_id": "siigo_ec",
            "nombre_modulo": "No configurado",
        },
    ]
    export_rows(rows, PLAN_FEATURE_FIELDS, output_format="csv", output=source)

    assert (
        transformation_main(
            [
                str(source),
                "--output",
                str(normalized),
                "--wide-output",
                str(wide),
                "--feature-rules",
                str(FEATURE_RULES),
                "--feature-rules-report",
                str(rules_report),
                "--feature-values-output",
                str(values),
                "--run-id",
                "run-001",
            ]
        )
        == 0
    )
    payload = json.loads(wide.read_text(encoding="utf-8"))
    assert payload[0]["usuarios_normales"] == 2
    assert payload[0]["usuarios_contador"] == 1
    assert payload[0]["usuarios_totales"] == 3
    assert payload[0]["no_configurado"] == 1
    report = json.loads(rules_report.read_text(encoding="utf-8"))
    assert report["match_counts"]["siigo_usuarios_y_contador"] == 1
    assert report["fallback_rows"] == 1
    assert "nomina_con_limite" in report["unused_rules"]
    value_rows = json.loads(values.read_text(encoding="utf-8"))
    normal_users = next(row for row in value_rows if row["feature_code"] == "usuarios_normales")
    assert normal_users["run_id"] == "run-001"
    assert normal_users["value_integer"] == 2
    assert normal_users["origin"] == "rule"


def test_cli_feature_rules_csv_uses_numeric_defaults_not_pd_na(tmp_path):
    source = tmp_path / "features.csv"
    normalized = tmp_path / "normalized.csv"
    wide = tmp_path / "wide.csv"
    export_rows(
        [
            {
                **_feature_row(),
                "competidor_id": "anfibius",
                "nombre_modulo": "Nómina",
            }
        ],
        PLAN_FEATURE_FIELDS,
        output_format="csv",
        output=source,
    )

    assert (
        transformation_main(
            [
                str(source),
                "--output",
                str(normalized),
                "--wide-output",
                str(wide),
                "--feature-rules",
                str(FEATURE_RULES),
            ]
        )
        == 0
    )
    with wide.open(encoding="utf-8", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["nomina_personas_max"] == "0"
    assert row["usuarios_totales"] == "0"
    assert "pd.NA" not in wide.read_text(encoding="utf-8")


def test_cli_csv_null_value_applies_to_main_and_wide_csv_outputs(tmp_path):
    source = tmp_path / "features.csv"
    normalized = tmp_path / "normalized.csv"
    wide = tmp_path / "wide.csv"
    export_rows(
        [
            {
                **_feature_row(),
                "competidor_id": "anfibius",
                "categoria_modulo": "",
                "nombre_modulo": "Nómina",
            }
        ],
        PLAN_FEATURE_FIELDS,
        output_format="csv",
        output=source,
    )

    assert (
        transformation_main(
            [
                str(source),
                "--output",
                str(normalized),
                "--wide-output",
                str(wide),
                "--feature-rules",
                str(FEATURE_RULES),
                "--csv-null-value",
                "NULL",
            ]
        )
        == 0
    )
    with normalized.open(encoding="utf-8", newline="") as stream:
        normalized_row = next(csv.DictReader(stream))
    with wide.open(encoding="utf-8", newline="") as stream:
        wide_row = next(csv.DictReader(stream))
    assert normalized_row["categoria_modulo"] == "NULL"
    assert wide_row["lista_modulos"] == "NULL"
    assert wide_row["nomina_personas_max"] == "0"


def test_cli_invalid_feature_rules_fail_before_any_output(tmp_path):
    source = tmp_path / "features.csv"
    normalized = tmp_path / "normalized.csv"
    wide = tmp_path / "wide.csv"
    rules = tmp_path / "invalid.json"
    export_rows([_feature_row()], PLAN_FEATURE_FIELDS, output_format="csv", output=source)
    rules.write_text('{"schema_version":2}', encoding="utf-8")

    assert (
        transformation_main(
            [
                str(source),
                "--output",
                str(normalized),
                "--wide-output",
                str(wide),
                "--feature-rules",
                str(rules),
            ]
        )
        == 2
    )
    assert not normalized.exists()
    assert not wide.exists()


def test_cli_feature_rules_require_a_feature_group(tmp_path):
    source = tmp_path / "reviews.csv"
    output = tmp_path / "normalized.csv"
    export_rows([_review_row()], REVIEW_FIELDS, output_format="csv", output=source)

    assert (
        transformation_main(
            [
                str(source),
                "--output",
                str(output),
                "--feature-rules",
                str(FEATURE_RULES),
            ]
        )
        == 2
    )
    assert not output.exists()


def test_cli_never_overwrites_the_feature_rules_input(tmp_path):
    source = tmp_path / "features.csv"
    output = tmp_path / "normalized.csv"
    rules = tmp_path / "rules.json"
    export_rows([_feature_row()], PLAN_FEATURE_FIELDS, output_format="csv", output=source)
    original = FEATURE_RULES.read_text(encoding="utf-8")
    rules.write_text(original, encoding="utf-8")

    assert (
        transformation_main(
            [
                str(source),
                "--output",
                str(output),
                "--wide-output",
                str(rules),
                "--feature-rules",
                str(rules),
                "--overwrite",
            ]
        )
        == 5
    )
    assert rules.read_text(encoding="utf-8") == original
    assert not output.exists()


def test_cli_writes_conflict_report_without_partial_datasets(tmp_path):
    source = tmp_path / "features.csv"
    output = tmp_path / "normalized.csv"
    wide = tmp_path / "wide.csv"
    report = tmp_path / "rules-report.json"
    rules = tmp_path / "rules.json"
    export_rows(
        [
            {
                **_feature_row(),
                "competidor_id": "anfibius",
                "nombre_modulo": "Nómina",
            }
        ],
        PLAN_FEATURE_FIELDS,
        output_format="csv",
        output=source,
    )
    payload = json.loads(FEATURE_RULES.read_text(encoding="utf-8"))
    duplicate = copy.deepcopy(payload["rule_sets"]["common"][1])
    duplicate["id"] = "nomina_duplicada"
    payload["rule_sets"]["common"].append(duplicate)
    rules.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    assert (
        transformation_main(
            [
                str(source),
                "--output",
                str(output),
                "--wide-output",
                str(wide),
                "--feature-rules",
                str(rules),
                "--feature-rules-report",
                str(report),
            ]
        )
        == 2
    )
    assert not output.exists()
    assert not wide.exists()
    assert len(json.loads(report.read_text(encoding="utf-8"))["multiple_matches"]) == 1
