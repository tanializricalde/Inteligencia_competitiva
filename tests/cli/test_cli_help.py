import pytest

from scraper_cli.cli import main


def test_root_help_lists_commands_examples_and_full_reference(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])

    output = capsys.readouterr().out
    assert exit_info.value.code == 0
    assert "subcomandos:" in output
    assert "validate-config" in output
    assert "plans" in output
    assert "reviews" in output
    assert "docs/cli/CLI_USAGE.md" in output


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("validate-config", "sin ejecutar fuentes"),
        ("plans", "--features-output PATH"),
        ("reviews", "máximo de registros por fuente"),
        ("all", "plans, plan_features y reviews"),
    ],
)
def test_subcommand_help_describes_its_behavior_and_examples(command, expected, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main([command, "--help"])

    output = capsys.readouterr().out
    assert exit_info.value.code == 0
    assert expected in output
    assert "Ejemplo" in output
