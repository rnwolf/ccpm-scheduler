"""The ccpm-scheduler command-line interface.

Designed to be equally usable by humans and AI agents:

- subcommands mirror the workflow: validate -> build -> check -> plot
- `--json` prints one machine-readable JSON document on stdout
  (`ccpm-scheduler schema report` describes the validate/check shape)
- exit codes are a contract: 0 = ok, 1 = the inputs/schedule have problems
  (the report is still emitted), 2 = the invocation itself is wrong
- never prompts, never colors output, deterministic: the same input always
  produces byte-identical output
- network input is either CSV files (tasks.csv resources.csv [calendar.csv])
  or a single JSON document (path or `-` for stdin) in the exchange format
  (`ccpm-scheduler schema network`)

Examples:

    ccpm-scheduler validate tasks.csv resources.csv calendar.csv
    ccpm-scheduler build tasks.csv resources.csv --calendar calendar.csv \\
        --out-dir plan --title "Website relaunch"
    ccpm-scheduler build project.json --out-dir plan --json
    echo '{"tasks": [...], "resources": [...]}' | ccpm-scheduler build - --json
    ccpm-scheduler check plan/schedule.csv tasks.csv resources.csv calendar.csv
    ccpm-scheduler plot plan/schedule.csv plan/gantt.png --resources resources.csv
    ccpm-scheduler schema network
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

from . import __version__, io
from .build import build_schedule
from .check import check_schedule
from .model import CcpmError
from .schema import SCHEMAS
from .validate import validate_network, report_lines


def _fail_usage(parser, message):
    parser.error(message)  # prints usage + message to stderr, exits 2


def _read_network(parser, inputs, calendar):
    """CSV (2-3 paths) or JSON (single path or '-')."""
    try:
        if len(inputs) == 1:
            if calendar:
                _fail_usage(parser, "--calendar applies to CSV input only; "
                                    "put calendar windows in the JSON document")
            src = inputs[0]
            text = sys.stdin.read() if src == "-" else open(
                src, encoding="utf-8").read()
            return io.network_from_json(text)
        if len(inputs) == 2:
            return io.load_network(inputs[0], inputs[1], calendar)
        if len(inputs) == 3:
            if calendar:
                _fail_usage(parser, "calendar given twice (positional and "
                                    "--calendar)")
            return io.load_network(inputs[0], inputs[1], inputs[2])
        _fail_usage(parser, "expected NETWORK.json | - | TASKS.csv "
                            "RESOURCES.csv [CALENDAR.csv]")
    except OSError as e:
        _fail_usage(parser, f"cannot read input: {e}")
    except (json.JSONDecodeError, ValueError) as e:
        _fail_usage(parser, f"bad JSON network: {e}")


def _report_json(net, rep):
    j = rep.to_json()
    j["issues"] = [w.to_json() for w in net.io_warnings] + j["issues"]
    j["errors"] = len(rep.errors)
    j["warnings"] = len(net.io_warnings) + len(rep.warnings)
    return j


def _emit(data):
    print(json.dumps(data, indent=2))


# ------------------------------------------------------------- subcommands

def cmd_validate(parser, args):
    net = _read_network(parser, args.inputs, args.calendar)
    rep = validate_network(net)
    if args.json:
        _emit(_report_json(net, rep))
        return 0 if rep.ok else 1
    lines, code = report_lines(net, rep)
    print("\n".join(lines))
    return code


def cmd_build(parser, args):
    net = _read_network(parser, args.inputs, args.calendar)
    rep = validate_network(net)
    if not rep.ok:
        if args.json:
            _emit(_report_json(net, rep))
        else:
            lines, _ = report_lines(net, rep)
            print("\n".join(lines))
        return 1
    try:
        result = build_schedule(net, args.title)
    except CcpmError as e:
        if args.json:
            _emit({"ok": False, "error": {"code": "E_UNSCHEDULABLE",
                                          "message": str(e)}})
        else:
            print(f"error: {e}", file=sys.stderr)
        return 1
    io.write_build_outputs(result, args.out_dir)
    files = {"schedule": os.path.join(args.out_dir, "schedule.csv"),
             "summary": os.path.join(args.out_dir, "summary.md")}
    if args.json:
        _emit({"ok": True, "title": result.title,
               "stats": dataclasses.asdict(result.stats),
               "files": files,
               "warnings": [w.to_json()
                            for w in net.io_warnings + rep.warnings],
               "schedule": result.schedule.to_json()})
    else:
        for w in net.io_warnings + rep.warnings:
            print(f"  warning: {w.message}", file=sys.stderr)
        print(result.stats.status_line(result.title))
    return 0


def cmd_check(parser, args):
    try:
        schedule = io.load_schedule(args.schedule)
    except OSError as e:
        _fail_usage(parser, f"cannot read schedule: {e}")
    net = _read_network(parser, args.inputs, args.calendar)
    rep = check_schedule(schedule, net)
    if args.json:
        _emit(_report_json(net, rep))
        return 0 if rep.ok else 1
    if not rep.ok:
        print(f"INVALID — {len(rep.errors)} violation(s):")
        for e in rep.errors:
            print(f"  - {e.message}")
        return 1
    print("VALID — all checks passed.")
    return 0


def cmd_plot(parser, args):
    from .plot import plot_schedule  # lazy: pulls in matplotlib
    try:
        schedule = io.load_schedule(args.schedule)
        resources = io.load_resources(args.resources) if args.resources else None
        calendar = io.load_calendar(args.calendar) if args.calendar else None
    except OSError as e:
        _fail_usage(parser, f"cannot read input: {e}")
    plot_schedule(schedule, args.out, title=args.title,
                  resources=resources, calendar=calendar,
                  show_util=not args.no_utilization,
                  show_links=not args.no_links,
                  critical_label=args.critical_label)
    if args.json:
        _emit({"ok": True, "wrote": args.out})
    else:
        print(f"wrote {args.out}")
    return 0


def cmd_schema(parser, args):
    _emit(SCHEMAS[args.which])
    return 0


# ------------------------------------------------------------- parser

def _add_network_inputs(sub):
    sub.add_argument("inputs", nargs="+", metavar="INPUT",
                     help="NETWORK.json | - (JSON on stdin) | "
                          "TASKS.csv RESOURCES.csv [CALENDAR.csv]")
    sub.add_argument("--calendar", metavar="CALENDAR.csv",
                     help="resource availability overrides "
                          "(resource_id, from, to, capacity on [from, to))")


def build_parser():
    p = argparse.ArgumentParser(
        prog="ccpm-scheduler",
        description="Deterministic Critical Chain Project Management (CCPM) "
                    "scheduler: validate a project network, build a "
                    "resource-leveled buffered schedule, verify it, and plot "
                    "a buffer-aware Gantt chart.",
        epilog="Exit codes: 0 = ok, 1 = problems found (report emitted), "
               "2 = usage error. Use --json for machine-readable output; "
               "`ccpm-scheduler schema network` describes the JSON input "
               "format.")
    p.add_argument("--version", action="version",
                   version=f"ccpm-scheduler {__version__}")
    subs = p.add_subparsers(dest="command", required=True)

    sp = subs.add_parser(
        "validate", help="check a project network before scheduling",
        description="Validate the network: ids, durations, dependency links, "
                    "cycles, resources, calendar. Exit 0 = schedulable "
                    "(warnings allowed), 1 = errors (each with a stable "
                    "issue code in --json mode).")
    _add_network_inputs(sp)
    sp.add_argument("--json", action="store_true",
                    help="machine-readable report on stdout")
    sp.set_defaults(func=cmd_validate)

    sp = subs.add_parser(
        "build", help="build the CCPM schedule (validates first)",
        description="Validate, then build the resource-leveled, buffered "
                    "schedule. Writes schedule.csv and summary.md to "
                    "--out-dir. Deterministic: the same input always yields "
                    "byte-identical output.")
    _add_network_inputs(sp)
    sp.add_argument("--out-dir", default=".", metavar="DIR",
                    help="where to write schedule.csv + summary.md "
                         "(default: current directory)")
    sp.add_argument("--title", default="CCPM schedule",
                    help='project title used in outputs (default: "CCPM schedule")')
    sp.add_argument("--json", action="store_true",
                    help="print stats, file paths, and the full schedule as JSON")
    sp.set_defaults(func=cmd_build)

    sp = subs.add_parser(
        "check", help="verify a schedule against its input network",
        description="Re-verify a produced schedule: precedence, resource "
                    "capacity (calendar-aware), buffer placement and link "
                    "discipline, chain continuity.")
    sp.add_argument("schedule", metavar="SCHEDULE.csv")
    _add_network_inputs(sp)
    sp.add_argument("--json", action="store_true",
                    help="machine-readable report on stdout")
    sp.set_defaults(func=cmd_check)

    sp = subs.add_parser(
        "plot", help="render a schedule as a Gantt chart PNG",
        description="Buffer-aware Gantt chart with dependency arrows and a "
                    "resource-utilization panel (red = over capacity, grey "
                    "hatch = unavailable).")
    sp.add_argument("schedule", metavar="SCHEDULE.csv")
    sp.add_argument("out", metavar="OUT.png")
    sp.add_argument("--resources", metavar="RESOURCES.csv",
                    help="real capacities for the utilization panel (default 1)")
    sp.add_argument("--calendar", metavar="CALENDAR.csv",
                    help="availability overrides, drawn as unavailable blocks")
    sp.add_argument("--title", default="CCPM Schedule")
    sp.add_argument("--critical-label", default="Critical chain",
                    help='legend label for critical bars (e.g. "Critical path" '
                         "for a plain CPM chart)")
    sp.add_argument("--no-utilization", action="store_true",
                    help="omit the resource-utilization panel")
    sp.add_argument("--no-links", action="store_true",
                    help="omit dependency arrows")
    sp.add_argument("--json", action="store_true",
                    help="print {ok, wrote} as JSON")
    sp.set_defaults(func=cmd_plot)

    sp = subs.add_parser(
        "schema", help="print a JSON Schema for the data contracts",
        description="Print the JSON Schema describing the network input "
                    "format, the schedule output, or the validation report.")
    sp.add_argument("which", nargs="?", default="network",
                    choices=sorted(SCHEMAS),
                    help="which contract to describe (default: network)")
    sp.set_defaults(func=cmd_schema)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    sys.exit(args.func(parser, args))


if __name__ == "__main__":
    main()
