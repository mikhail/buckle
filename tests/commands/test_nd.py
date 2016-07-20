import mock
import re
import socket
import struct
import time

import pytest  # flake8: noqa

from fixtures import executable_factory, run_as_child

from nd_toolbelt.commands import nd


class TestNdCommand:
    def test_nd_update_and_no_update_cannot_be_set_together(self, capfd):
        """ Handle the case where --update and --no-update are both called as options """

        with pytest.raises(SystemExit):
            nd.main(['nd', '--update', '--no-update', 'version'])
        stdout, stderr = capfd.readouterr()
        assert '--no-update: not allowed with argument --update' in stderr

    def test_with_no_args(self, capfd, executable_factory, run_as_child):
        """ Handle nd being passed no command or namespace """

        executable_factory('nd-help', '#!/bin/bash\necho -n $@')
        run_as_child(nd.main, ['nd'])
        stdout, stderr = capfd.readouterr()
        assert '' in stdout

    def test_with_command(self, capfd, executable_factory, run_as_child):
        """ Handle executing nd command in path """

        executable_factory('nd-my-command', '#!/bin/bash\necho my command output')
        run_as_child(nd.main, ['nd', 'my-command'])
        stdout, stderr = capfd.readouterr()
        assert stdout == 'my command output\n'

    def test_command_with_argument(self, capfd, executable_factory, run_as_child):
        """ Handle executing nd command in path with arguments passed from nd """

        executable_factory('nd-my-command', '#!/bin/echo')
        run_as_child(nd.main, ['nd', 'my-command', '--my-option', 'my-argument'])
        stdout, stderr = capfd.readouterr()
        assert '--my-option my-argument' in stdout

    def test_with_namespace(self, capfd, executable_factory, run_as_child):
        """ Handle executing nd command in path """

        executable_factory('nd-help', '#!/bin/bash\necho -n $@')
        executable_factory('nd-my-namespace~my-command')

        run_as_child(nd.main, ['nd', 'my-namespace'])
        stdout, stderr = capfd.readouterr()
        assert stdout == 'my-namespace'

    def test_help_for_command(self, capfd, executable_factory, run_as_child):
        """ Handle executing nd-help for command in path """

        executable_factory('nd-help', '#!/bin/bash\necho -n $@')
        run_as_child(nd.main, ['nd', 'help', 'my-command'])
        stdout, stderr = capfd.readouterr()
        assert stdout == 'my-command'

    def test_command_or_namespace_not_found(self, capfd):
        """ Handle being given a command or namespace not in path """

        with pytest.raises(SystemExit):
            nd.main(['nd', 'missing'])
        stdout, stderr = capfd.readouterr()
        assert "Command 'missing' not found." in stderr

    def test_command_or_namespace_help_not_found(self, capfd, executable_factory):
        """ Handle being given a command or namespace for help not in path """

        executable_factory('nd-help', '#!/bin/bash\necho -n $@')
        executable_factory('nd-my-namespace~my-command')

        with pytest.raises(SystemExit):
            nd.main(['nd', 'my-namespace', 'missing', 'help'])
        stdout, stderr = capfd.readouterr()
        assert "Command or namespace 'missing' not found in 'my-namespace'" in stderr

    def test_with_command_that_cannot_be_run(self, capfd, executable_factory, run_as_child):
        """ Handle the case where a command cannot be run """

        executable_factory('nd-my-command')
        with pytest.raises(run_as_child.ChildError) as exc_info:
            run_as_child(nd.main, ['nd', 'my-command'])
        stdout, stderr = capfd.readouterr()
        assert 'SystemExit' in str(exc_info.value)
        assert "Command 'nd-my-command' could not be run" in stderr


class TestNdCheckSystemClock(object):
    @staticmethod
    @pytest.yield_fixture
    def ntp_response_factory():
        with mock.patch.object(socket, 'socket') as mock_socket:
            def factory(offset):
                time_since_1900 = int(time.time()) + 2208988800
                encoded_time = struct.pack('!12I', *(([0] * 10) + [time_since_1900 + offset] + [0]))

                mock_socket.return_value.recvfrom.return_value = (encoded_time, None)

            yield factory

            mock_socket.assert_called_with(socket.AF_INET, socket.SOCK_DGRAM)

    def test_nothing_happens_if_time_is_accurate(self, capfd, ntp_response_factory):
        """ Running nd with accurate system time does not print to stderr """

        ntp_response_factory(0)
        nd.check_system_clock(check_clock_freq=0)
        stdout, stderr = capfd.readouterr()
        assert 'WARNING:' not in stderr and 'ERROR:' not in stderr

    def test_warning_if_system_clock_is_too_far_behind(self, capfd, ntp_response_factory):
        """ Running nd with system time too far behind the threshold prints to stderr """

        ntp_response_factory(120)
        nd.check_system_clock(check_clock_freq=0)
        stdout, stderr = capfd.readouterr()
        assert re.search(r'The system clock is behind by \d+', stderr)

    def test_warning_if_system_clock_is_too_far_ahead(self, capfd, ntp_response_factory):
        """ Running nd with system time too far ahead the threshold prints to stderr """

        ntp_response_factory(-120)
        nd.check_system_clock(check_clock_freq=0)
        stdout, stderr = capfd.readouterr()
        assert re.search(r'The system clock is behind by -\d+', stderr)

    def test_nd_continues_if_get_ntp_time_times_out(self, capfd):
        """ Handle ntp request for current time timing out """

        with mock.patch.object(socket, 'socket') as mock_socket:
            mock_socket.return_value.recvfrom.side_effect = socket.timeout()
            nd.check_system_clock(check_clock_freq=0)
            stdout, stderr = capfd.readouterr()
            assert 'timed out.' in stderr

    def test_nd_continues_if_get_ntp_time_raises_socket_error(self, capfd):
        """ Handle ntp request for socket raising an error """

        with mock.patch.object(socket, 'socket') as mock_socket:
            mock_socket.return_value.sendto.side_effect = socket.error()
            nd.check_system_clock(check_clock_freq=0)
            stdout, stderr = capfd.readouterr()
            assert 'Error checking network time, exception: ' in stderr
