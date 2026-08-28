"""本地 Backend Supervisor 的纯函数与 CLI Contract。"""

from pathlib import Path

from run import (
    apply_local_environment_defaults,
    build_parser,
    dotenv_declared_names,
    parse_compose_service_states,
)


def test_local_backend_parser_defaults_are_safe() -> None:
    arguments = build_parser().parse_args([])

    assert arguments.host == "127.0.0.1"
    assert arguments.port == 8000
    assert arguments.reload is False
    assert arguments.no_docker is False
    assert arguments.skip_migrations is False
    assert arguments.keep_infra is False


def test_compose_state_parser_accepts_line_and_array_json() -> None:
    line_output = (
        '{"Service":"postgres","State":"running","Health":"healthy"}\n'
        '{"Service":"ignored","State":"exited","Health":""}\n'
    )
    array_output = (
        '[{"Service":"postgres","State":"running","Health":"healthy"},'
        '{"Service":"ignored","State":"exited","Health":""}]'
    )

    assert parse_compose_service_states(line_output)["postgres"]["Health"] == "healthy"
    assert parse_compose_service_states(array_output)["ignored"]["State"] == "exited"


def test_local_defaults_do_not_override_shell_or_dotenv(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "NEXUSMCP_DATABASE_URL=postgresql+asyncpg://custom\n"
        "export NEXUSMCP_LOCAL_TENANT_ID=custom-tenant\n",
        encoding="utf-8",
    )
    environment = {"NEXUSMCP_CONTROL_PLANE_ENABLED": "false"}

    apply_local_environment_defaults(env_file, environment)

    assert dotenv_declared_names(env_file) == {
        "NEXUSMCP_DATABASE_URL",
        "NEXUSMCP_LOCAL_TENANT_ID",
    }
    assert "NEXUSMCP_DATABASE_URL" not in environment
    assert "NEXUSMCP_LOCAL_TENANT_ID" not in environment
    assert environment["NEXUSMCP_CONTROL_PLANE_ENABLED"] == "false"
    assert environment["NEXUSMCP_CATALOG_BACKEND"] == "postgresql"
