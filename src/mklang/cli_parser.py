"""The `mklang` argparse tree.

Handlers are injected by the caller (``cli.main``) so this module never imports
the commands — the parser stays cycle-free by construction.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping

from . import __version__
from .logs import LEVELS

Handler = Callable[[argparse.Namespace], int]


def build_parser(handlers: Mapping[str, Handler]) -> argparse.ArgumentParser:
    formatter = argparse.RawDescriptionHelpFormatter
    ap = argparse.ArgumentParser(
        prog="mklang",
        description="Author, validate, test, and run declarative LLM state machines.",
        epilog=(
            "Typical workflow:\n"
            "  mklang init\n"
            "  mklang test machines/hello.mkl --script machines/hello.test.yaml\n"
            "  mklang lint --strict machines/hello.mkl\n"
            "  mklang run machines/hello.mkl --set task=hello"
        ),
        formatter_class=formatter,
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=False)

    def logging_args(parser):
        parser.add_argument(
            "--log-level",
            choices=LEVELS,
            default=None,
            help="process log level on stderr (default: MKLANG_LOG_LEVEL or warning)",
        )

    def presentation_args(parser, *, formats=("auto", "text", "json")):
        parser.add_argument(
            "--format",
            choices=formats,
            default="auto",
            help="output format (default: terminal-aware auto)",
        )
        parser.add_argument(
            "--color",
            choices=("auto", "always", "never"),
            default="auto",
            help="color policy for text output; NO_COLOR is honored",
        )

    r = sub.add_parser("run", help="execute a machine against a provider")
    r.add_argument("machine", help="machine path or registered machine name")
    r.add_argument("--config", default=None, help="runtime config (auto-discovered when omitted)")
    r.add_argument("--provider", default=None, help="override the config's `active` provider")
    r.add_argument("--set", action="append", default=[], metavar="k.path=value")
    r.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="cost budget: halt once total tokens reach this",
    )
    r.add_argument(
        "--checkpoint",
        default=None,
        metavar="PATH",
        help="on budget exhaustion suspend and write a resumable checkpoint here "
        "(contains the full context in plaintext; written 0600, see SPEC §11)",
    )
    r.add_argument(
        "--hitl",
        action="store_true",
        help="a fired escalate gate suspends for human review (checkpoint defaults "
        "to the XDG state root when --checkpoint is omitted); "
        "reply via `mklang resume --set`",
    )
    r.add_argument(
        "--strict",
        action="store_true",
        help="refuse to run a document whose mklang: version is unsupported "
        "(version-unsupported); default is a warning",
    )
    r.add_argument(
        "--workspace",
        default=None,
        metavar="DIR",
        help="workspace root for the fs data tools (default: MKLANG_FS_ROOT or the "
        "current directory — ADR 0024)",
    )
    r.add_argument(
        "--allow-write",
        action="store_true",
        help="grant write_file access to real disk under the workspace "
        "(default off in headless runs; MKLANG_FS_WRITE=1 is the env equivalent)",
    )
    r.add_argument(
        "--on-truncate",
        choices=("report", "halt"),
        default="report",
        help="when produce hits max_tokens/length: annotate the trace (report, default) "
        "or halt with state-error: output-truncated (halt) — ADR 0018",
    )
    r.add_argument(
        "--untrusted-flow",
        choices=("report", "halt"),
        default="report",
        help="when a gate judged over external data routes into an effectful tool "
        "state: annotate the trace (report, default) or refuse the effect with "
        "untrusted-control-flow (halt) — SPEC §6 / ADR 0030",
    )
    presentation_args(r)
    logging_args(r)
    r.set_defaults(fn=handlers["run"])

    s = sub.add_parser("resume", help="resume a suspended run from a checkpoint")
    s.add_argument("checkpoint", help="checkpoint JSON written by run/resume")
    s.add_argument("--config", default=None, help="runtime config (auto-discovered when omitted)")
    s.add_argument("--provider", default=None, help="override the config's `active` provider")
    s.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="k.path=value",
        help="inject values (e.g. the human reply) into the suspended run's context",
    )
    s.add_argument(
        "--hitl",
        action="store_true",
        help="keep suspending on escalate gates even if the checkpoint didn't record it",
    )
    s.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="new cost budget (total, including tokens spent before the suspend)",
    )
    s.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="new step budget (total, including steps spent before the suspend)",
    )
    s.add_argument("--machine", default=None, help="machine path override (if the .mkl moved)")
    s.add_argument(
        "--checkpoint",
        dest="checkpoint_out",
        default=None,
        metavar="PATH",
        help="where to write the checkpoint on re-suspension (default: overwrite the input)",
    )
    s.add_argument("--force", action="store_true", help="resume even if the machine file changed")
    s.add_argument(
        "--on-truncate",
        choices=("report", "halt"),
        default="report",
        help="produce truncation policy on resume (same as run; ADR 0018)",
    )
    s.add_argument(
        "--untrusted-flow",
        choices=("report", "halt"),
        default="report",
        help="control-flow-taint policy on resume (same as run; ADR 0030)",
    )
    presentation_args(s)
    logging_args(s)
    s.set_defaults(fn=handlers["resume"])

    co = sub.add_parser("console", help="agent-first console TUI")
    co.add_argument("--config", default=None, help="runtime config (auto-discovered when omitted)")
    co.add_argument("--provider", default=None, help="override the config's `active` provider")
    co.add_argument(
        "--workspace",
        default=None,
        metavar="DIR",
        help="where authored machines live; writes are confined here "
        "(default: the current directory)",
    )
    co.add_argument(
        "--agent",
        default=None,
        metavar="FILE.mkl",
        help="swap the console's brain with your own machine (same tool contract)",
    )
    co.add_argument(
        "--continue",
        dest="continue_session",
        action="store_true",
        help="reopen the most recent session (history, spend, consents)",
    )
    co.add_argument("--session", default=None, metavar="ID", help="reopen a specific session by id")
    co.set_defaults(fn=handlers["console"])

    m = sub.add_parser("machines", help="list commissionable machines (stdlib, plugins) as JSON")
    m.add_argument(
        "--dir",
        default=None,
        metavar="DIR",
        help="also list the .mkl machines of a project directory",
    )
    presentation_args(m)
    logging_args(m)
    m.set_defaults(fn=handlers["machines"])

    ini = sub.add_parser("init", help="scaffold project or user config without overwriting files")
    ini.add_argument(
        "--user", action="store_true", help="initialize the XDG user host instead of a project"
    )
    ini.add_argument(
        "--dir", default=".", metavar="DIR", help="project root (default: current directory)"
    )
    presentation_args(ini)
    logging_args(ini)
    ini.set_defaults(fn=handlers["init"])

    d = sub.add_parser(
        "doctor", help="diagnose the resolved setup: config layer, env, keys, machine roots"
    )
    d.add_argument("--config", default=None, help="runtime config (auto-discovered when omitted)")
    presentation_args(d)
    logging_args(d)
    d.set_defaults(fn=handlers["doctor"])

    c = sub.add_parser("check", help="validate machines (schema + semantics)")
    c.add_argument("machines", nargs="+")
    c.add_argument(
        "--strict",
        action="store_true",
        help="treat an unsupported mklang: version as an error (version-unsupported)",
    )
    presentation_args(c)
    logging_args(c)
    c.set_defaults(fn=handlers["check"])

    li = sub.add_parser("lint", help="check + static analysis (dead gates, unread outputs, typos)")
    li.add_argument("machines", nargs="+")
    li.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when static lint findings exist (--llm findings stay advisory)",
    )
    li.add_argument(
        "--llm",
        action="store_true",
        help="probe prose-gate ambiguity with a live judge (ADR 0010) — "
        "costs real tokens; advisory, non-deterministic",
    )
    li.add_argument("--config", default=None, help="runtime config (auto-discovered when omitted)")
    li.add_argument("--provider", default=None, help="override the config's `active` provider")
    li.add_argument(
        "--llm-samples",
        type=int,
        default=5,
        metavar="K",
        help="synthetic outputs per multi-gate state (default 5)",
    )
    li.add_argument(
        "--llm-repeats",
        type=int,
        default=3,
        metavar="R",
        help="judge repeats per synthetic output (default 3)",
    )
    presentation_args(li)
    logging_args(li)
    li.set_defaults(fn=handlers["lint"])

    t = sub.add_parser(
        "test",
        help="run scenario tests against a machine with a scripted LLM (no API keys)",
    )
    t.add_argument("machine")
    t.add_argument(
        "--script",
        required=True,
        metavar="FILE",
        help="a .test.yaml of named scenarios (scripted llm/tools/hooks + expect)",
    )
    presentation_args(t)
    logging_args(t)
    t.set_defaults(fn=handlers["test"])

    return ap
