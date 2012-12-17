#!/usr/bin/python -u
# Copyright (c) 2010-2012 OpenStack, LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from subprocess import call, Popen
from unittest import main, TestCase
from uuid import uuid4
import os
import time
import shutil

from swiftclient import client

#from swift.common import direct_client
from test.probe.common import kill_server, kill_servers, reset_environment, \
    start_server


def collect_info(path_list):
    """
    Recursive collect dirs and files in path_list directory.

    :param path_list: start directory for collecting
    :return files_list, dir_list: tuple of included
    directories and files
    """
    files_list = []
    dir_list = []
    for path in path_list:
        temp_files_list = []
        temp_dir_list = []
        for root, dirs, files in os.walk(path):
            temp_files_list += files
            temp_dir_list += dirs
        files_list.append(temp_files_list)
        dir_list.append(temp_dir_list)
    return files_list, dir_list


def find_max_occupancy_node(dir_list):
    """
    Find node with maximum occupancy.

    :param list_dir: list of directories for each node.
    :return number: number node in list_dir
    """
    count = 0
    number = 0
    lenght = 0
    for dirs in dir_list:
        if lenght < len(dirs):
            lenght = len(dirs)
            number = count
        count += 1
    return number


class TestReplicatorFunctions(TestCase):
    """
    Class for testing replicators and replication servers.

    By default configuration - replication servers not used.
    For testing separete replication servers servers need to change
    ring's files using set_info command or new ring's files with
    different port values.
    """
    def setUp(self):
        """
        Reset all environment and start all servers.
        """
        (self.pids, self.port2server, self.account_ring, self.container_ring,
         self.object_ring, self.url, self.token,
         self.account, self.configs) = reset_environment()

    def tearDown(self):
        """
        Stop all servers.
        """
        kill_servers(self.port2server, self.pids)

    def test_main(self):
        # Create one account, container and object file.
        # Find node with account, container and object replicas.
        # Delete all directories and files from this node (device).
        # Wait 60 seconds and check replication results.
        # Delete directories and files in objects storage without
        # deleting file "hashes.pkl".
        # Check, that files not replicated.
        # Delete file "hashes.pkl".
        # Check, that all files were replicated.
        path_list = ['/srv/1/node/sdb1/', '/srv/2/node/sdb2/',
                     '/srv/3/node/sdb3/', '/srv/4/node/sdb4/']

        # Put data to storage nodes
        container = 'container-%s' % uuid4()
        client.put_container(self.url, self.token, container)

        obj = 'object-%s' % uuid4()
        client.put_object(self.url, self.token, container, obj, 'VERIFY')

        # Get all data file information
        (files_list, dirs_list) = collect_info(path_list)
        num = find_max_occupancy_node(dirs_list)
        test_node = path_list[num]
        test_node_files_list = []
        for files in files_list[num]:
            if not files.endswith('.pending'):
                test_node_files_list.append(files)
        test_node_dirs_list = dirs_list[num]
        # Run all replicators
        processes = []

        for num in xrange(1, 9):
            for server in ['object-replicator',
                           'container-replicator',
                           'account-replicator']:
                if not os.path.exists(self.configs[server] % (num)):
                    continue
                processes.append(Popen(['swift-%s' % (server),
                                        self.configs[server] % (num),
                                        'forever']))

        # Delete some files
        for dirs in os.listdir(test_node):
            shutil.rmtree(test_node+dirs)

        self.assertFalse(os.listdir(test_node))

        # We will keep trying these tests until they pass for up to 60s
        begin = time.time()
        while True:
            (new_files_list, new_dirs_list) = collect_info([test_node])

            try:
                # Check replicate files and dirs
                for files in test_node_files_list:
                    self.assertTrue(files in new_files_list[0])

                for dirs in test_node_dirs_list:
                    self.assertTrue(dirs in new_dirs_list[0])
                break
            except Exception:
                if time.time() - begin > 60:
                    raise
                time.sleep(1)

        # Check behavior by deleting hashes.pkl file
        for dirs in os.listdir(test_node + 'objects/'):
            for input_dirs in os.listdir(test_node + 'objects/' + dirs):
                eval_dirs = '/' + input_dirs
                if os.path.isdir(test_node + 'objects/' + dirs + eval_dirs):
                    shutil.rmtree(test_node + 'objects/' + dirs + eval_dirs)

        # We will keep trying these tests until they pass for up to 60s
        begin = time.time()
        while True:
            try:
                for dirs in os.listdir(test_node + 'objects/'):
                    for input_dirs in os.listdir(
                            test_node + 'objects/' + dirs):
                        self.assertFalse(os.path.isdir(test_node + 'objects/' +
                                         dirs + '/' + input_dirs))
                break
            except Exception:
                if time.time() - begin > 60:
                    raise
                time.sleep(1)

        for dirs in os.listdir(test_node + 'objects/'):
            os.remove(test_node + 'objects/' + dirs + '/hashes.pkl')

        # We will keep trying these tests until they pass for up to 60s
        begin = time.time()
        while True:
            try:
                (new_files_list, new_dirs_list) = collect_info([test_node])

                # Check replicate files and dirs
                for files in test_node_files_list:
                    self.assertTrue(files in new_files_list[0])

                for dirs in test_node_dirs_list:
                    self.assertTrue(dirs in new_dirs_list[0])
                break
            except Exception:
                if time.time() - begin > 60:
                    raise
                time.sleep(1)

        for process in processes:
            process.kill()


if __name__ == '__main__':
    main()
