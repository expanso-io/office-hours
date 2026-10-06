from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def make_executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def copy_script(project: Path, name: str) -> None:
    scripts = project / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "scripts" / name, scripts / name)


def run(project: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*args],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_cloud_start_without_local_profile_never_calls_docker(tmp_path: Path) -> None:
    project = tmp_path / "project"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    copy_script(project, "democtl.sh")
    copy_script(project, "cloudctl.sh")

    docker_log = tmp_path / "docker.log"
    make_executable(
        fake_bin / "docker",
        '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$DOCKER_CALL_LOG"\n',
    )
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_CALL_LOG": str(docker_log),
    }

    result = run(project, "./scripts/democtl.sh", "start", "cloud", "baseline", env=env)

    assert result.returncode == 2
    assert "SKIP: no project-local Cloud profile" in (result.stdout + result.stderr)
    assert not docker_log.exists()
    assert not (project / ".runtime").exists()


def test_failed_cloud_start_rolls_back_runtime_and_docker_state(tmp_path: Path) -> None:
    project = tmp_path / "project"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    copy_script(project, "democtl.sh")
    make_executable(
        project / "scripts" / "cloudctl.sh",
        """#!/usr/bin/env bash
case "$1" in
  preflight) exit 0 ;;
  start) touch "$FAKE_PROJECT/.fake-edge"; exit 17 ;;
  stop) rm -f "$FAKE_PROJECT/.fake-edge"; exit 0 ;;
  *) exit 0 ;;
esac
""",
    )
    make_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
case " $* " in
  *" up "*) touch "$FAKE_PROJECT/.fake-compose" ;;
  *" down "*) rm -f "$FAKE_PROJECT/.fake-compose" ;;
esac
""",
    )
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_PROJECT": str(project),
    }

    result = run(project, "./scripts/democtl.sh", "start", "cloud", "baseline", env=env)

    assert result.returncode == 17
    assert not (project / ".runtime").exists()
    assert not (project / ".fake-compose").exists()
    assert not (project / ".fake-edge").exists()


def test_cloud_verify_without_local_profile_is_nonzero(tmp_path: Path) -> None:
    project = tmp_path / "project"
    copy_script(project, "cloudctl.sh")

    result = run(project, "./scripts/cloudctl.sh", "verify", env=os.environ.copy())

    assert result.returncode == 2
    assert "SKIP: no project-local Cloud profile" in (result.stdout + result.stderr)


def test_env_bootstraps_isolated_profile_without_passing_key_to_cli(tmp_path: Path) -> None:
    project = tmp_path / "project"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    copy_script(project, "cloudctl.sh")
    env_file = project / ".env"
    env_file.write_text(
        "EXPANSO_CLOUD_ENDPOINT=https://demo.example:9010\nEXPANSO_CLOUD_API_KEY=exp_ak_demo_only\n"
    )
    env_file.chmod(0o600)
    cli_log = tmp_path / "cli.log"
    make_executable(
        fake_bin / "expanso-cli",
        '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$CLI_LOG"\nexit 0\n',
    )

    result = run(
        project,
        "./scripts/cloudctl.sh",
        "preflight",
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "CLI_LOG": str(cli_log)},
    )

    profile = (
        project / ".cloud-state/cli-home/.expanso/cli-client/profiles/signal-not-noise-demo.yaml"
    )
    assert result.returncode == 1
    assert profile.stat().st_mode & 0o777 == 0o600
    assert "api_key: exp_ak_demo_only" in profile.read_text()
    assert "exp_ak_demo_only" not in cli_log.read_text()


def test_cloud_bootstrap_creates_project_local_edge_identity(tmp_path: Path) -> None:
    project = tmp_path / "project"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    copy_script(project, "cloudctl.sh")
    env_file = project / ".env"
    env_file.write_text(
        "EXPANSO_CLOUD_ENDPOINT=https://demo.example:9010\n"
        "EXPANSO_CLOUD_API_KEY=exp_ak_demo_only\n"
        "EXPANSO_EDGE_BOOTSTRAP_TOKEN=exp_bk_demo_only\n"
    )
    env_file.chmod(0o600)
    make_executable(
        fake_bin / "expanso-cli",
        "#!/usr/bin/env bash\n"
        'if [[ " $* " == *" --format json "* ]]; then echo \'[]\'; fi\n'
        "exit 0\n",
    )
    make_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
for ((i = 1; i <= $#; i++)); do
  if [[ "${!i}" == "-v" ]]; then
    next=$((i + 1)); mount="${!next}"; data_dir="${mount%%:*}"
    if [[ "$mount" == *":/data" ]]; then mkdir -p "$data_dir"; touch "$data_dir/identity"; fi
  fi
done
exit 0
""",
    )

    result = run(
        project,
        "./scripts/cloudctl.sh",
        "bootstrap",
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )

    edge = project / ".cloud-state/node-01"
    assert result.returncode == 0
    assert (edge / "identity").is_file()
    assert edge.stat().st_mode & 0o777 == 0o700


def test_cloud_stop_failure_propagates_after_local_cleanup(tmp_path: Path) -> None:
    project = tmp_path / "project"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    copy_script(project, "democtl.sh")
    make_executable(
        project / "scripts" / "cloudctl.sh",
        """#!/usr/bin/env bash
case "$1" in
  stop) exit 23 ;;
  stop-local) exit 0 ;;
  *) exit 0 ;;
esac
""",
    )
    make_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
case " $* " in
  *" down "*) rm -f "$FAKE_PROJECT/.fake-compose" ;;
esac
""",
    )
    runtime = project / ".runtime"
    runtime.mkdir()
    (runtime / "mode").write_text("cloud\n")
    (runtime / "demo.env").write_text("DEMO_MODE=cloud\n")
    (project / ".fake-compose").touch()
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_PROJECT": str(project),
    }

    result = run(project, "./scripts/democtl.sh", "stop", env=env)

    assert result.returncode == 23
    assert runtime.exists()
    assert (runtime / "mode").read_text() == "cloud\n"
    assert not (project / ".fake-compose").exists()


def test_local_stop_is_idempotent_without_cloud_credentials(tmp_path: Path) -> None:
    project = tmp_path / "project"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    copy_script(project, "democtl.sh")
    make_executable(
        project / "scripts" / "cloudctl.sh",
        """#!/usr/bin/env bash
case "$1" in
  stop-local) exit 0 ;;
  *) exit 31 ;;
esac
""",
    )
    make_executable(fake_bin / "docker", "#!/usr/bin/env bash\nexit 0\n")
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"}

    first = run(project, "./scripts/democtl.sh", "stop", env=env)
    second = run(project, "./scripts/democtl.sh", "stop", env=env)

    assert first.returncode == 0
    assert second.returncode == 0


def test_cloud_cleanup_verification_rejects_nonterminal_execution(tmp_path: Path) -> None:
    project = tmp_path / "project"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    copy_script(project, "cloudctl.sh")
    profiles = project / ".cloud-state" / "cli-home" / ".expanso" / "cli-client" / "profiles"
    profiles.mkdir(parents=True)
    profile = profiles / "signal-not-noise-demo.yaml"
    profile.write_text("profile: test\\n")
    profile.chmod(0o600)
    make_executable(
        fake_bin / "expanso-cli",
        """#!/usr/bin/env bash
case "$*" in
  *" status") exit 0 ;;
  *" job list"*)
    printf '%s\\n' '[{"id":"job-active","version":1,"spec":{"name":"demo-signal-not-noise","labels":{"demo":"signal-not-noise"}},"status":{"state":{"state_type":"stopped"}}}]'
    ;;
  *" execution list"*)
    printf '%s\\n' '[{"status":{"observed_state":{"state_type":"starting"}}}]'
    ;;
  *) printf '%s\\n' '[]' ;;
esac
""",
    )
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"}

    result = run(project, "./scripts/cloudctl.sh", "verify-stopped", env=env)

    assert result.returncode == 1
    assert "matching active job or execution remains" in (result.stdout + result.stderr)


def test_cloud_verify_rejects_mismatched_requested_variant(tmp_path: Path) -> None:
    project = tmp_path / "project"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    copy_script(project, "cloudctl.sh")
    profiles = project / ".cloud-state" / "cli-home" / ".expanso" / "cli-client" / "profiles"
    profiles.mkdir(parents=True)
    profile = profiles / "signal-not-noise-demo.yaml"
    profile.write_text("profile: test\n")
    profile.chmod(0o600)
    edge = project / ".cloud-state" / "node-01"
    edge.mkdir()
    edge.chmod(0o700)
    make_executable(
        fake_bin / "expanso-cli",
        """#!/usr/bin/env bash
case "$*" in
  *" status") exit 0 ;;
  *" job list"*)
    printf '%s\n' '[{"id":"job-1","version":7,"spec":{"name":"demo-signal-not-noise","labels":{"demo":"signal-not-noise","variant":"baseline"},"selector":{"match_labels":{"demo":"signal-not-noise"}}},"status":{"state":{"state_type":"running"}}}]'
    ;;
  *) printf '%s\n' '[]' ;;
esac
""",
    )
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"}

    result = run(project, "./scripts/cloudctl.sh", "verify", "filtered", env=env)

    assert result.returncode == 1
    assert "exact labeled filtered job not found" in (result.stdout + result.stderr)
