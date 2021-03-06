import mock
import os
import textwrap

import pytest  # flake8: noqa

from fixtures import executable_factory, run_as_child, readout

from buckle.commands import help


def make_help_command(message):
    """ Makes the contents of the test help commands """
    return "#!/bin/bash\ncat << 'EOF'\n{}\nEOF".format(textwrap.dedent(message))


@pytest.fixture(autouse=True)
def set_toolbelt_name(monkeypatch):
    monkeypatch.setenv('BUCKLE_TOOLBELT_NAME', 'nd')


class TestCommandHelp:
    def test_calls_commands_with_help_flag(self, executable_factory, readout, run_as_child):
        """ Print help for all commands parses descriptions from generic commands' --help """

        executable_factory('nd-my-command', '#!/bin/echo')
        with readout() as message:
            run_as_child(help.main, ['nd', 'my-command'])
        assert '--help' in message

    def test_with_missing_command(self):
        """ Running help for a missing command prints an error """

        with pytest.raises(SystemExit) as exc_info:
            help.main(['nd', 'my-missing-command'])
        assert "Command 'my-missing-command' not found." in str(exc_info.value)

    def test_with_command_cannot_be_run(self, executable_factory, run_as_child):
        """ Handle the case where a command cannot be run """

        executable_factory('nd-my-command', '')
        with pytest.raises(run_as_child.ChildError) as exc_info:
            run_as_child(help.main, ['nd', 'my-command'])
        assert 'SystemExit' in str(exc_info.value)
        assert "Command 'nd-my-command' could not be run" in str(exc_info.value)

    def test_command_help_not_found(self, executable_factory):
        """ Handle being given a command or namespace for help not in path """

        executable_factory('nd-my-namespace~my-command')

        with pytest.raises(SystemExit) as exc_info:
            help.main(['nd', 'my-namespace', 'missing', 'help'])
        assert "Command or namespace 'missing' not found in 'my-namespace'" in str(exc_info.value)

    def test_excluded_command(self, executable_factory, monkeypatch):
        """ Help returns an error when applied to excluded commands. """

        monkeypatch.setenv('BUCKLE_HELP_OPTS_ND', '-X nd-my-excluded-command')
        executable_factory('nd-my-excluded-command', '#!/bin/echo\nFAIL')
        with pytest.raises(SystemExit) as exc_info:
            help.main(['nd', 'my-excluded-command'])
        assert "Command 'nd-my-excluded-command' is excluded from help" in str(exc_info.value)


class TestNamespaceHelp:
    @staticmethod
    @pytest.fixture(autouse=True)
    def set_minimal_path(monkeypatch):
        monkeypatch.setenv('PATH', '/usr/bin:/bin')

    @staticmethod
    @pytest.fixture(autouse=True)
    def mock_terminal_size(monkeypatch):
        monkeypatch.setenv('COLUMNS', 120)

    @staticmethod
    @pytest.fixture(autouse=True)
    def set_toolbelt_name(monkeypatch):
        monkeypatch.setenv('BUCKLE_TOOLBELT_NAME', 'nd')

    def test_with_command_with_empty_help(self, executable_factory, readout):
        """ Handle the case where help returns empty string """

        executable_factory('nd-my-command', make_help_command(''))
        with readout() as message:
            help.main(['nd'])
        assert 'my-command   <help not found>' in message

    def test_with_no_args(self, executable_factory, readout):
        """ Running help without a command or namespace prints help of commands on path """

        executable_factory('nd-my-namespace~my-command', make_help_command('my help message'))
        with readout() as message:
            help.main(['nd'])
        assert 'Showing help for all' in message
        assert 'my-namespace my-command   my help message' in message

    def test_with_no_args_and_no_nd_commands(self):
        """ Running help when no nd commands are present prints an error """

        with pytest.raises(SystemExit) as exc_info:
            help.main(['nd'])
        assert 'No nd commands found on path. Check your $PATH.' in str(exc_info.value)

    def test_parses_argparse_generated_help(self, executable_factory, readout):
        """ Print help for all commands parses argparse's description from its generated help """

        executable_factory('nd-my-command', make_help_command("""\
            usage: ...

            my help message"""), dedent=False)
        with readout() as message:
            help.main(['nd'])
        assert 'my-command   my help message' in message

    def test_parses_nonargparse_generated_help(self, executable_factory, readout):
        """ Print help for all commands parses descriptions from generic commands' --help """

        executable_factory('nd-my-command', make_help_command('my help message'))
        with readout() as message:
            help.main(['nd'])
        assert 'my-command   my help message' in message

    def test_with_namespace(self, executable_factory, readout):
        """ Running help on a namespace shows help for each command in the namespace """

        executable_factory('nd-my-namespace~my-command', make_help_command('my help message'))
        with readout() as message:
            help.main(['nd', 'my-namespace'])
        assert 'my-namespace my-command   my help message' in message

    def test_with_failing_command(self, executable_factory, readout):
        """ Handle the case where a command returns non-zero exit status """

        executable_factory('nd-my-command', '#!/bin/bash\nexit 1')
        with readout() as message:
            help.main(['nd'])
        assert 'my-command   <help not found>' in message

    def test_without_columns_envvar(self, executable_factory, monkeypatch, readout):
        """ Running help on a namespace shows help for each command in the namespace """

        monkeypatch.delenv('COLUMNS')

        with mock.patch.object(os, 'popen') as popen:
            popen.return_value.read.return_value = '30 40'

            executable_factory('nd-my-command',
                               make_help_command('my really really really long help message'))
            with readout() as message:
                help.main(['nd'])
            assert '...' in message

            popen.assert_called_with('stty size', 'r')

    def test_excluded_command(self, executable_factory, monkeypatch, readout):
        """ Help returns an error when applied to excluded commands. """

        monkeypatch.setenv('BUCKLE_HELP_OPTS_ND', '-X nd-my-excluded-command')
        executable_factory('nd-my-included-command')
        executable_factory('nd-my-excluded-command', '#!/bin/echo\nFAIL')
        with readout() as message:
            help.main(['nd'])
        assert 'my-included-command' in message
        assert 'my-excluded-command' not in message

    def test_output_is_sorted_alphabetically_by_namespace(self, executable_factory, readout):
        """ Help returns an error when applied to excluded commands. """

        executable_factory('nd-my-a-command')
        executable_factory('nd-my-z-command')
        executable_factory('nd-my-a-namespace~my-command')
        executable_factory('nd-my-namespace~my-subnamespace~my-command')
        executable_factory('nd-my-z-namespace~my-command')

        with readout() as output:
            help.main(['nd'])
        message = str(output)
        assert (message.index('my-a-command') <
                message.index('my-z-command') <
                message.index('my-a-namespace my-command') <
                message.index('my-namespace my-subnamespace my-command') <
                message.index('my-z-namespace my-command'))

    def test_excludes_completion_commands(self, executable_factory, readout):
        """ Doesn't report autocompletion scripts """

        executable_factory('nd-my-command')
        executable_factory('nd-my-command.completion')
        executable_factory('nd-my-command.completion.sh')
        with readout() as message:
            help.main(['nd'])
        assert 'my-command' in message
        assert 'my-command.completion' not in message

    def test_slow_help_is_skipped(self, executable_factory, readout):
        """ Skip printing help info for a slow help """

        executable_factory('nd-my-command', '#!/usr/bin/env bash\nsleep 10\necho my help message')
        with readout() as message:
            with mock.patch.object(help, 'HELP_TIMEOUT', 0):
                help.main(['nd'])
        assert 'my-command   <help not found>' in message
