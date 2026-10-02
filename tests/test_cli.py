import io

from autotyper import cli


def test_dry_run_prints_transcript_and_summary(tmp_path, capsys):
    f = tmp_path / "t.txt"
    f.write_text("hola mundo")
    code = cli.main([str(f), "--dry-run", "--seed", "1", "--error-rate", "0"])
    out = capsys.readouterr().out
    assert code == 0
    assert "hola mundo" in out
    assert "duration:" in out


def test_dry_run_reads_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("desde stdin"))
    code = cli.main(["-", "--dry-run", "--seed", "1", "--error-rate", "0"])
    assert code == 0
    assert "desde stdin" in capsys.readouterr().out


def test_dry_run_verbose_lists_events(tmp_path, capsys):
    f = tmp_path / "t.txt"
    f.write_text("ab")
    cli.main([str(f), "--dry-run", "--verbose", "--seed", "1", "--error-rate", "0"])
    out = capsys.readouterr().out
    assert "'a'" in out and "'b'" in out and "hold" in out


def test_missing_file_returns_1(capsys):
    assert cli.main(["/no/such/file.txt", "--dry-run"]) == 1
    assert "not found" in capsys.readouterr().err


def test_empty_text_returns_1(tmp_path, capsys):
    f = tmp_path / "t.txt"
    f.write_text("   \n")
    assert cli.main([str(f), "--dry-run"]) == 1
    assert "empty" in capsys.readouterr().err


def test_profile_and_flags_combine(tmp_path, capsys):
    prof = tmp_path / "p.yaml"
    prof.write_text("cps: 2\nerror_rate: 0\nthink_pause_rate: 0\n")
    f = tmp_path / "t.txt"
    f.write_text("a" * 20)
    cli.main([str(f), "--dry-run", "--profile", str(prof), "--seed", "1", "--cps", "20"])
    out = capsys.readouterr().out
    # 20 chars at 20 cps is about 1 s, not 10 s
    line = next(l for l in out.splitlines() if l.startswith("duration:"))
    seconds = float(line.split()[1])
    assert seconds < 3


def test_invalid_config_returns_1(tmp_path, capsys):
    f = tmp_path / "t.txt"
    f.write_text("hola")
    assert cli.main([str(f), "--dry-run", "--layout", "fr"]) == 1
    assert "layout" in capsys.readouterr().err


def test_real_run_uses_injected_dependencies(tmp_path, monkeypatch, capsys):
    f = tmp_path / "t.txt"
    f.write_text("ab")
    pressed = []

    class FakeInjector:
        def press(self, key, hold_s):
            pressed.append(key)

    class FakeHotkeys:
        def __init__(self, *a, **k):
            self.started = False

        def start(self):
            self.started = True

        def stop(self):
            pass

    monkeypatch.setattr(cli, "PynputInjector", FakeInjector)
    monkeypatch.setattr(cli, "HotkeyListener", FakeHotkeys)
    monkeypatch.setattr(cli, "accessibility_trusted", lambda prompt=False: True)
    monkeypatch.setattr(cli, "frontmost_app_name", lambda: "Google Chrome")
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    code = cli.main([str(f), "--seed", "1", "--error-rate", "0", "--countdown", "0"])
    assert code == 0
    assert pressed == ["a", "b"]
    assert "done" in capsys.readouterr().out


def test_real_run_without_accessibility_returns_2(tmp_path, monkeypatch, capsys):
    f = tmp_path / "t.txt"
    f.write_text("ab")
    calls = []

    def fake_trusted(prompt=False):
        calls.append(prompt)
        return False

    monkeypatch.setattr(cli, "accessibility_trusted", fake_trusted)
    assert cli.main([str(f), "--countdown", "0"]) == 2
    assert "Accessibility" in capsys.readouterr().err
    assert calls == [True], "the CLI must ask macOS to show its permission prompt"


def _fake_env(monkeypatch):
    class FakeHotkeys:
        def __init__(self, *a, **k):
            pass

        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr(cli, "HotkeyListener", FakeHotkeys)
    monkeypatch.setattr(cli, "accessibility_trusted", lambda prompt=False: True)
    monkeypatch.setattr(cli, "frontmost_app_name", lambda: "Google Chrome")


def test_ctrl_c_during_countdown_exits_130_without_traceback(tmp_path, monkeypatch, capsys):
    f = tmp_path / "t.txt"
    f.write_text("ab")
    _fake_env(monkeypatch)

    def sleep(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", sleep)
    assert cli.main([str(f), "--countdown", "3"]) == 130
    out = capsys.readouterr().out
    assert "aborted" in out


def test_ctrl_c_during_typing_exits_130_and_reports_progress(tmp_path, monkeypatch, capsys):
    f = tmp_path / "t.txt"
    f.write_text("abc")
    _fake_env(monkeypatch)
    pressed = []

    class FakeInjector:
        def press(self, key, hold_s):
            pressed.append(key)
            if len(pressed) == 2:
                raise KeyboardInterrupt

    monkeypatch.setattr(cli, "PynputInjector", FakeInjector)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    assert cli.main([str(f), "--countdown", "0", "--error-rate", "0"]) == 130
    assert "aborted after 1 keystrokes" in capsys.readouterr().out


def test_injector_failure_exits_1_with_short_message(tmp_path, monkeypatch, capsys):
    f = tmp_path / "t.txt"
    f.write_text("ab")
    _fake_env(monkeypatch)

    class BrokenInjector:
        def press(self, key, hold_s):
            raise RuntimeError("event tap failed")

    monkeypatch.setattr(cli, "PynputInjector", BrokenInjector)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    assert cli.main([str(f), "--countdown", "0", "--error-rate", "0"]) == 1
    err = capsys.readouterr().err
    assert "event tap failed" in err
    assert "Traceback" not in err


def test_invalid_yaml_profile_exits_1(tmp_path, capsys):
    prof = tmp_path / "p.yaml"
    prof.write_text("cps: [unclosed\n")
    f = tmp_path / "t.txt"
    f.write_text("ab")
    assert cli.main([str(f), "--dry-run", "--profile", str(prof)]) == 1
    assert "profile" in capsys.readouterr().err


def test_wpm_flag_sets_speed(tmp_path, capsys):
    f = tmp_path / "t.txt"
    f.write_text("a" * 60)
    cli.main([str(f), "--dry-run", "--seed", "1", "--error-rate", "0", "--think-pause-rate", "0", "--wpm", "120"])
    line = next(l for l in capsys.readouterr().out.splitlines() if l.startswith("duration:"))
    assert float(line.split()[1]) < 9


def test_duration_flag_fits_the_text(tmp_path, capsys):
    f = tmp_path / "t.txt"
    f.write_text("palabra " * 50)
    cli.main([str(f), "--dry-run", "--seed", "1", "--duration", "30"])
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if l.startswith("duration:"))
    assert abs(float(line.split()[1]) - 30) < 3
    assert "fitted cps:" in out


def test_duration_with_cps_is_rejected(tmp_path, capsys):
    f = tmp_path / "t.txt"
    f.write_text("hola")
    assert cli.main([str(f), "--dry-run", "--duration", "10", "--cps", "5"]) == 1
    assert "--duration" in capsys.readouterr().err


def test_progress_line_is_printed_during_real_run(tmp_path, monkeypatch, capsys):
    f = tmp_path / "t.txt"
    f.write_text("abc")
    _fake_env(monkeypatch)

    class FakeInjector:
        def press(self, key, hold_s):
            pass

    monkeypatch.setattr(cli, "PynputInjector", FakeInjector)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    cli.main([str(f), "--countdown", "0", "--error-rate", "0", "--seed", "1"])
    assert "3/3" in capsys.readouterr().out
