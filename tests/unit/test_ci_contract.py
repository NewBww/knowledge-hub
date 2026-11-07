"""Runner-local paths must be initialized after GitHub assigns a runner."""
from pathlib import Path


def test_job_environment_uses_only_pre_runner_contexts():
    workflow = Path(__file__).parents[2] / '.github/workflows/ci.yml'
    before_steps = workflow.read_text().split('    steps:', 1)[0]
    assert '${{ runner.' not in before_steps


def test_ci_pins_a_supported_explicit_intel_runner():
    workflow = (Path(__file__).parents[2] / '.github/workflows/ci.yml').read_text()
    assert '    runs-on: macos-15-intel\n' in workflow
    assert 'macos-14' not in workflow


def test_ci_initializes_and_persists_isolated_paths(tmp_path):
    import os
    import subprocess
    workflow = (Path(__file__).parents[2] / '.github/workflows/ci.yml').read_text()
    step = workflow.split('      - name: Prepare isolated scratch\n', 1)[1].split('      - name:', 1)[0]
    assert '        run: |\n' in step
    script = '\n'.join(line[10:] for line in step.split('        run: |\n', 1)[1].splitlines())
    runner = tmp_path / 'runner space'
    runner.mkdir()
    github_env = tmp_path / 'github-env'
    subprocess.run(['/bin/bash', '-eu', '-c', script], check=True,
                   env={'PATH': os.defpath, 'RUNNER_TEMP': str(runner), 'GITHUB_ENV': str(github_env)})
    exported = dict(line.split('=', 1) for line in github_env.read_text().splitlines())
    assert set(exported) == {'TMPDIR', 'KNOWLEDGE_HUB_DATA_DIR'}
    for path in exported.values():
        assert Path(path).is_relative_to(runner)
        assert Path(path).is_dir()
    assert exported['TMPDIR'] != exported['KNOWLEDGE_HUB_DATA_DIR']
