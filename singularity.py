# Based on the Docker connection plugin 
#
# (c) 2014, Lorin Hochstein
# (c) 2015, Leendert Brouwer (https://github.com/objectified)
# (c) 2015, Toshio Kuratomi <tkuratomi@ansible.com>
# Copyright (c) 2017 Ansible Project
# (c) 2018 Rupert Nash, The University of Edinburgh 
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = """
    author:
        - Rupert Nash
    connection: singularity
    short_description: Run tasks in singularity instance
    description:
        - Run commands or put/fetch files to a singularity instance
    version_added: "2.5"
    options:
      remote_addr:
        description:
            - The name of the instance you want to access
        default: inventory_hostname
        vars:
            - name: ansible_host
            - name: ansible_singularity_host
      singularity_extra_args:
        description: Extra arguments to pass to the singularity command line
        default: ''

"""

import distutils.spawn
import os
import os.path
import subprocess
import re

from distutils.version import LooseVersion

import ansible.constants as C
from ansible.errors import AnsibleError, AnsibleFileNotFound
from ansible.module_utils.six.moves import shlex_quote
from ansible.module_utils._text import to_bytes, to_native, to_text
from ansible.plugins.connection import ConnectionBase, BUFSIZE


try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


class Connection(ConnectionBase):
    ''' Local singularity based connections '''

    transport = 'singularity'
    has_pipelining = True

    def __init__(self, play_context, new_stdin, *args, **kwargs):
        super(Connection, self).__init__(play_context, new_stdin, *args, **kwargs)

        if 'singularity_command' in kwargs:
            self.singularity_cmd = kwargs['singularity_command']
        else:
            self.singularity_cmd = distutils.spawn.find_executable('singularity')
            if not self.singularity_cmd:
                raise AnsibleError("singularity command not found in PATH")

        if self._play_context.remote_user is not None:
            display.warning(u'Singularity does not support different users inside the container')

    @staticmethod
    def _sanitize_version(version):
        return re.sub(u'[^0-9a-zA-Z.]', u'', version)

    def _get_singularity_version(self):
        cmd = [self.singularity_cmd, '--version']
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        cmd_output, err = p.communicate()
        err = p.returncode
        cmd_output = to_native(cmd_output)
        for line in to_text(cmd_output, errors='surrogate_or_strict').split(u'\n'):
            return self._sanitize_version(line)        

    
    def _build_exec_cmd(self, cmd):
        """ Build the local singularity exec command to run cmd on remote_host

            If remote_user is available and is supported by the singularity
            version we are using, it will be provided to singularity exec.
        """

        local_cmd = [self.singularity_cmd]
        extras = self.get_option('singularity_extra_args')
        if extras:
            local_cmd += extras.split(' ')

        local_cmd += [b'exec', self.get_option('remote_addr')] + cmd
        return local_cmd

    def _connect(self, port=None):
        """ Connect to the instance. Nothing to do """
        super(Connection, self)._connect()
        if not self._connected:            
            self._connected = True

    def exec_command(self, cmd, in_data=None, sudoable=False):
        """ Run a command inside the running instance """
        local_cmd = self._build_exec_cmd([self._play_context.executable, '-c', cmd])

        display.vvv("EXEC %s" % (local_cmd,), host=self.get_option('remote_addr'))
        local_cmd = [to_bytes(i, errors='surrogate_or_strict') for i in local_cmd]
        p = subprocess.Popen(local_cmd, shell=False, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        stdout, stderr = p.communicate(in_data)
        return (p.returncode, stdout, stderr)

    def _prefix_login_path(self, remote_path):
        ''' Make sure that we put files into a standard path

            If a path is relative, then we need to choose where to put it.
            ssh chooses $HOME but we aren't guaranteed that a home dir will
            exist in any given chroot.  So for now we're choosing "/" instead.
            This also happens to be the former default.

            Can revisit using $HOME instead if it's a problem
        '''
        if not remote_path.startswith(os.path.sep):
            remote_path = os.path.join(os.path.sep, remote_path)
        return os.path.normpath(remote_path)

    def put_file(self, in_path, out_path):
        """ Transfer a file from local to instance """
        display.vvv("PUT %s TO %s" % (in_path, out_path), host=self.get_option('remote_addr'))
        
        out_path = self._prefix_login_path(out_path)
        if not os.path.exists(to_bytes(in_path, errors='surrogate_or_strict')):
            raise AnsibleFileNotFound(
                "file or module does not exist: %s" % to_native(in_path))

        out_path = shlex_quote(out_path)
        # Could reasonably transfer via /tmp but will rely on existing functionality
        args = self._build_exec_cmd([self._play_context.executable, "-c", "dd of=%s bs=%s" % (out_path, BUFSIZE)])
        args = [to_bytes(i, errors='surrogate_or_strict') for i in args]
        with open(to_bytes(in_path, errors='surrogate_or_strict'), 'rb') as in_file:
            try:
                p = subprocess.Popen(args, stdin=in_file,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except OSError:
                raise AnsibleError("singularity connection requires dd command in the container to put files")
            stdout, stderr = p.communicate()

            if p.returncode != 0:
                raise AnsibleError("failed to transfer file %s to %s:\n%s\n%s" %
                                   (to_native(in_path), to_native(out_path), to_native(stdout), to_native(stderr)))

    def fetch_file(self, in_path, out_path):
        """ Fetch a file from container to local. """
        super(Connection, self).fetch_file(in_path, out_path)
        display.vvv("FETCH %s TO %s" % (in_path, out_path), host=self.get_option('remote_addr'))

        in_path = self._prefix_login_path(in_path)

        # Could reasonably transfer via /tmp but will rely on existing functionality
        args = self._build_exec_cmd([self._play_context.executable, "-c", "dd if=%s bs=%s" % (in_path, BUFSIZE)])
        args = [to_bytes(i, errors='surrogate_or_strict') for i in args]
        with open(to_bytes(out_path, errors='surrogate_or_strict'), 'wb') as out_file:
            try:
                p = subprocess.Popen(args, stdin=subprocess.PIPE,
                                     stdout=out_file, stderr=subprocess.PIPE)
            except OSError:
                raise AnsibleError("singularity connection requires dd command in the container to put files")
            stdout, stderr = p.communicate()

            if p.returncode != 0:
                raise AnsibleError("failed to fetch file %s to %s:\n%s\n%s" % (in_path, out_path, stdout, stderr))


    def close(self):
        """ Terminate the connection. Nothing to do for singularity"""
        super(Connection, self).close()
        self._connected = False
