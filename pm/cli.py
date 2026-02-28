"""
pm CLI - Lumia Package Manager.

Pacman-style interface for managing Lumia plugins.

Usage:
    pm -S <plugin>[@version]     Install plugin
    pm -R <plugin>               Remove plugin
    pm -U [plugin]               Upgrade plugin(s)
    pm -Q                        List installed plugins
    pm -Ql <plugin>              List plugin files
    pm -Ss <query>               Search registry
    pm -Si <plugin>              Show plugin info
"""

import argparse
import sys


class PMError(Exception):
    """Base exception for pm errors."""

    pass


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser with pacman-style flags."""
    parser = argparse.ArgumentParser(
        prog="pm",
        description="Lumia Package Manager - Pacman-style plugin manager",
        add_help=False,
    )

    # Operation flags (mutually exclusive)
    ops = parser.add_mutually_exclusive_group()
    ops.add_argument("-S", "--sync", action="store_true", help="Install plugin")
    ops.add_argument("-R", "--remove", action="store_true", help="Remove plugin")
    ops.add_argument("-U", "--upgrade", action="store_true", help="Upgrade plugin(s)")
    ops.add_argument("-Q", "--query", action="store_true", help="Query installed")
    ops.add_argument("-h", "--help", action="store_true", help="Show help")

    # Query sub-flags
    parser.add_argument("-l", "--list", action="store_true", help="List files (-Ql)")
    parser.add_argument("-s", "--search", action="store_true", help="Search (-Ss)")
    parser.add_argument("-i", "--info", action="store_true", help="Show info (-Si)")

    # Common options
    parser.add_argument("--purge", action="store_true", help="Remove config on -R")
    parser.add_argument(
        "--noconfirm", action="store_true", help="Skip confirmation prompts"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    # Positional arguments
    parser.add_argument("targets", nargs="*", help="Plugin names or queries")

    return parser


def print_help():
    """Print help message."""
    help_text = """
pm - Lumia Package Manager

Usage:
    pm -S <plugin>[@version]     Install plugin
    pm -R <plugin>               Remove plugin
    pm -U [plugin]               Upgrade plugin(s)
    pm -Q                        List installed plugins
    pm -Ql <plugin>              List plugin files
    pm -Ss <query>               Search registry
    pm -Si <plugin>              Show plugin info

Options:
    --purge                      Remove config on -R
    --noconfirm                  Skip confirmation prompts
    -v, --verbose                Verbose output
    -h, --help                   Show this help
"""
    print(help_text.strip())


def main():
    """Main entry point for pm CLI."""
    parser = create_parser()
    args = parser.parse_args()

    try:
        # Show help
        if args.help or (
            not args.sync
            and not args.remove
            and not args.upgrade
            and not args.query
        ):
            print_help()
            return 0

        # Route to appropriate command
        if args.sync:
            # -S: Install
            from pm.commands.install import install_command

            return install_command(args)

        elif args.remove:
            # -R: Remove
            from pm.commands.remove import remove_command

            return remove_command(args)

        elif args.upgrade:
            # -U: Upgrade
            from pm.commands.upgrade import upgrade_command

            return upgrade_command(args)

        elif args.query:
            # -Q: Query
            from pm.commands.query import query_command

            return query_command(args)

    except PMError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

