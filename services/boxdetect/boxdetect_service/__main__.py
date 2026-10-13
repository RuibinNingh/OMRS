"""独立框选服务的 serve／probe 命令行入口。"""
import argparse

from . import probe, server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name, module in [('serve', server), ('probe', probe)]:
        command = commands.add_parser(name, description=module.__doc__)
        module.add_arguments(command)
        command.set_defaults(handler=module.run)
    args = parser.parse_args(argv)
    args.handler(args)


if __name__ == '__main__':
    main()
