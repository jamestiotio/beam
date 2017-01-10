#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""End-to-end test result verifiers

A set of verifiers that are used in end-to-end tests to verify state/output
of test pipeline job. Customized verifier should extend
`hamcrest.core.base_matcher.BaseMatcher` and override _matches.
"""

import hashlib
import logging

from apache_beam.io.fileio import TextFileSource
from apache_beam.runners.runner import PipelineState
from apache_beam.utils import retry
from hamcrest.core.base_matcher import BaseMatcher

MAX_RETRIES = 4


class PipelineStateMatcher(BaseMatcher):
  """Matcher that verify pipeline job terminated in expected state

  Matcher compares the actual pipeline terminate state with expected.
  By default, `PipelineState.DONE` is used as expected state.
  """

  def __init__(self, expected_state=PipelineState.DONE):
    self.expected_state = expected_state

  def _matches(self, pipeline_result):
    return pipeline_result.current_state() == self.expected_state

  def describe_to(self, description):
    description \
      .append_text("Test pipeline expected terminated in state: ") \
      .append_text(self.expected_state)

  def describe_mismatch(self, pipeline_result, mismatch_description):
    mismatch_description \
      .append_text("Test pipeline job terminated in state: ") \
      .append_text(pipeline_result.current_state())


def retry_on_fileio_error(exception):
  """Filter allowing retries on file I/O errors."""
  if isinstance(exception, RuntimeError) or \
          isinstance(exception, IOError):
    # GCS I/O raises RuntimeError and local filesystem I/O
    # raises IOError when file reading is failed.
    return True
  else:
    return False


class FileChecksumMatcher(BaseMatcher):
  """Matcher that verifies file(s) content by comparing file checksum.

  Use fileio to fetch file(s) from given path. Currently, fileio supports
  local filesystem and GCS.

  File checksum is a SHA-1 hash computed from content of file(s).
  """

  def __init__(self, file_path, expected_checksum):
    self.file_path = file_path
    self.expected_checksum = expected_checksum

  @retry.with_exponential_backoff(num_retries=MAX_RETRIES,
                                  retry_filter=retry_on_fileio_error)
  def _read_with_retry(self):
    """Read path with retry if I/O failed"""
    source = TextFileSource(self.file_path)
    read_lines = []
    with source.reader() as reader:
      for line in reader:
        read_lines.append(line)
    return read_lines

  def _matches(self, _):
    # Read from given file(s) path
    read_lines = self._read_with_retry()

    # Compute checksum
    read_lines.sort()
    m = hashlib.new('sha1')
    for line in read_lines:
      m.update(line)
    self.checksum, num_lines = (m.hexdigest(), len(read_lines))
    logging.info('Read from given path %s, %d lines, checksum: %s.',
                 self.file_path, num_lines, self.checksum)
    return self.checksum == self.expected_checksum

  def describe_to(self, description):
    description \
      .append_text("Expected checksum is ") \
      .append_text(self.expected_checksum)

  def describe_mismatch(self, pipeline_result, mismatch_description):
    mismatch_description \
      .append_text("Actual checksum is ") \
      .append_text(self.checksum)
