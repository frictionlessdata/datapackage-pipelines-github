# -*- coding: utf-8 -*-
from __future__ import division
from __future__ import print_function
from __future__ import absolute_import
from __future__ import unicode_literals

from datapackage_pipelines.specs import pipelines


def test_pipeline():
    '''Tests that what we want for open data is correct.'''
    for pipeline in pipelines():
        if pipeline.pipeline_id == './tests/env/github/issues/001_test-issue-dont-close':
            return
    assert False
