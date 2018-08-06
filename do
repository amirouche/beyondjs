#!/usr/bin/env python3
"""do a Makefile replacement with bells, whistles and whatnot..."""
import platform
import os
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path
from shutil import which
from subprocess import DEVNULL
from subprocess import check_call
from subprocess import CalledProcessError
from tempfile import mkstemp


QUOTE_A = '  “The best way to predict the future is to invent it.” Alan Kay'


def RecursiveDict():
    return defaultdict(RecursiveDict)


def sudo(command):
    check_call('sudo ' + command, shell=True)


def apt(package):
    print("* Installing {}".format(package))
    sudo("apt install {}".format(package))


def download(url):
    filepath, _ = urllib.request.urlretrieve(url)
    return filepath


# populate abstraction to handle package management task.
# It's some kind of multiple dispatch.
manager = RecursiveDict()


manager['Linux']['Ubuntu']['18.04']['pkg-config'] = lambda: apt("pkg-config")


def pkgconfig(library):
    require('pkg-config')
    print("* Checking for the presence of '{}' system library".format(library))
    try:
        run('pkg-config --libs {}'.format(library))
    except CalledProcessError:
        print("* System library '{}' missing".format(library))
        return False
    else:
        return True


def require(command):
    print("* Checking for the presence of '{}' command".format(command))
    if which(command) is None:
        print("* Command {} not found".format(command))
        import debug;
        manager[system][distro][version][command]()

def require_lib(library):
    require("pkg-config")
    print("* Checking for the presence of '{}' library".format(command))
    if pkgconfig(library) is None:
        print("* Library {} not found")
        manager[system][distro][version][library]()


def require_ubuntu_sqlite():
    print("* Installing sqlite")
    apt("sqlite libsqlite0-dev")


manager['Linux']['Ubuntu']['18.04']['sqlite'] = require_ubuntu_sqlite


manager['Linux']['Ubuntu']['18.04']['python2'] = lambda: apt('python')


def require_ubuntu_foundationdb():
    require("python2")
    print('* Installing foundationdb')
    _, filepath = mkstemp(prefix='do-')
    FOUNDATION_CLIENT_DEB = 'https://bit.ly/2FJDch0'
    filepath = download(FOUNDATION_CLIENT_DEB)
    sudo('dpkg -i {}'.format(filepath))
    FOUNDATION_SERVER_DEB = 'https://bit.ly/2rq6tbs'
    filepath = download(FOUNDATION_SERVER_DEB)
    sudo('dpkg -i {}'.format(filepath))


manager['Linux']['Ubuntu']['18.04']['fdbcli'] = require_ubuntu_foundationdb


commands = RecursiveDict()


def run(command):
    if os.environ.get('DEBUG'):
        print('$ {}'.format(command))
        check_call(command, shell=True)
    else:
        check_call(command, stdout=DEVNULL, stderr=DEVNULL, shell=True)


def dev_prepare(args):
    global system, distro, version
    if args in (['--help'], ['-h']):
        print('Setup the host for *development* and spawn a shell in a virtualenv')
        raise SystemExit(0)
    require('git')
    system = platform.system()
    distro, version, _ = platform.linux_distribution()
    print('* Detected {} {} {}'.format(system, distro, version))
    require('sqlite')
    print('* Prepare pyenv, see https://github.com/pyenv/pyenv')
    pyenv = Path(os.path.expanduser('~/.pyenv'))
    if not pyenv.exists():
        print('* Installing pyenv from git, see https://github.com/pyenv/pyenv')
        run('git clone https://github.com/pyenv/pyenv.git {}'.format(pyenv))
    else:
        print('* Updating pyenv')
        run('cd {} && git pull origin master'.format(pyenv))
    # override the variable to point to pyenv command
    pyenv = pyenv / 'bin' / 'pyenv'
    # install correct python version
    with Path('./.python-version').open() as f:
        python_version = f.read().strip()
    print('* Installing {} via pyenv'.format(python_version))
    run('{} install --skip-existing'.format(pyenv))
    print('* Installing latest version of pipenv via pip, see https://github.com/pypa/pipenv/')
    run('{} exec pip3 install --upgrade pipenv'.format(pyenv))
    print('* Preparing the virtual environment via pipenv')
    run('PIPENV_VENV_IN_PROJECT=1 {} exec pipenv install --dev'.format(pyenv))
    require('fdbcli')  # FIXME
    print()
    print(QUOTE_A)
    print()
    pipenv = pyenv.parent.parent / "versions" / python_version / "bin" / "pipenv"
    print('Now run: {}  shell'.format(pipenv))


commands['dev']['prepare'] = dev_prepare


def doc_build_html(args):
    if args in (['--help'], ['-h']):
        print('Build the documentation')
        raise SystemExit(0)
    print('* Building documentation in html format')
    require('make')
    require('pipenv')
    run('cd doc && make html')
    print('* Open the documentation with your favorite browser: xdg-open doc/build/html/index.html &')


commands['doc']['build']['html'] = doc_build_html


# CLI helpers

def _usage(callable_or_commands, root):
    if callable(callable_or_commands):
        print(' '.join(root))
    else:
        for name, commands in callable_or_commands.items():
            _usage(commands, root + [name])


def usage():
    print('Usage:')
    _usage(commands, ['  do'])
    print('\nUse --help after a command to know what it does.')
    print('Do that before actually running the command please!')


def raise_command_not_found():
    print('Command not found!')
    usage()
    raise SystemExit(2)


def exec(callable_or_commands, args):
    if callable(callable_or_commands):
        callable_or_commands(args)
    else:
        try:
            subcommand = args[0]
        except IndexError:
            raise_command_not_found()
        try:
            commands = callable_or_commands[subcommand]
        except KeyError:
            raise_command_not_found()
        else:
            exec(commands, args[1:])


def main():
    if sys.argv[1:] in ([], ['--help'], ['-h']):
        usage()
    else:
        exec(commands, sys.argv[1:])


if __name__ == '__main__':
    main()
