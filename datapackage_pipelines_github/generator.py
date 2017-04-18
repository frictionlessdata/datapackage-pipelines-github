import os
import json
from posixpath import join as urljoin

import requests

from datapackage_pipelines.generators import \
    GeneratorBase, slugify, steps

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), 'schema.json')


class Generator(GeneratorBase):

    @classmethod
    def get_schema(cls):
        return json.load(open(SCHEMA_FILE))

    @classmethod
    def generate_pipeline(cls, source):
        for pipeline_id_prefix, defs in source.items():
            repository = defs['repository']
            pull_requests = defs.get('pull-requests', False)
            closed = defs.get('closed', False)
            pipeline_id_format = defs.get('pipeline-id-format', '{issue-id:03}_{title-slug}')

            issues_url = 'https://api.github.com/repos/{}/issues'.format(repository)
            resp = requests.get(issues_url)

            if resp.status_code == 200:
                for issue in resp.json():

                    if issue['state'] != 'open' and not closed:
                        continue
                    if 'pull-requests' in issue and not pull_requests:
                        continue

                    title_slug = slugify(issue['title'])
                    fmt = {
                        'issue-id': issue['number'],
                        'title-slug': title_slug
                    }
                    pipeline_id = pipeline_id_format.format(**fmt)
                    pipeline_id = urljoin(pipeline_id_prefix, pipeline_id)
                    pipeline_details = {
                        'title': issue['title'],
                        'pipeline': steps(['github.waiting-for-implementation'])
                    }
                    if issue.get('body') is not None:
                        pipeline_details['description'] = issue['body']
                    yield pipeline_id, pipeline_details
