import os
import json
import time
import codecs
import urllib.parse
import copy
import re
import logging
import tarfile
import shutil
from posixpath import join as urljoin

import requests
import yaml

from datapackage_pipelines.generators import \
    GeneratorBase, slugify, steps

logging.getLogger("requests").setLevel(logging.WARNING)

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), 'schema.json')


class CachedGetter(object):

    def __init__(self, ttl=300):
        self.cache = {}
        self.ttl = ttl
        self.gh_url_base = 'https://api.github.com'
        self.params = {}

        auth_token = os.environ.get('GITHUB_AUTH_TOKEN')
        if auth_token is not None:
            self.params['access_token'] = auth_token

    def get(self, url, params={}):
        return self.raw_get(self.gh_url_base+url, params)

    def raw_get(self, url, params={}):
        # Prepare URL
        query_params = copy.copy(self.params)
        query_params.update(params)
        query = urllib.parse.urlencode(sorted(query_params.items()))
        url = '?'.join([url, query])

        # Check cache
        if url in self.cache:
            ret, timestamp = self.cache[url]
            if time.time() - timestamp > self.ttl:
                self.cache[url] = (ret, time.time())
                return ret
            else:
                del self.cache[url]

        # Hit network
        resp = requests.get(url)
        if resp.status_code == 200:
            ret = resp.json()
            self.cache[url] = (ret, time.time())
            return ret
        return None


URL_GETTER = CachedGetter()


class Generator(GeneratorBase):

    @classmethod
    def get_schema(cls):
        return json.load(open(SCHEMA_FILE))

    @classmethod
    def handle_issue(cls, issue, issue_policy):
        pipeline_id_format = issue_policy.get('pipeline-id-format', 'issue/{issue-id:03}_{title-slug}')
        pipeline_steps = steps(['github.waiting-for-implementation'])
        yield pipeline_id_format, pipeline_steps

    @classmethod
    def handle_pr(cls, repository, base_path, issue, pr_policy):
        pipeline_id_format = pr_policy.get('pipeline-id-format', 'pr/{issue-id:03}_{title-slug}')

        pull_request_url = '/repos/{}/pulls/{}'.format(repository, issue['number'])
        pull_request = URL_GETTER.get(pull_request_url)

        # Get PR head and determine if local or remote PR
        head = '{}/{}'.format(pull_request['head']['repo']['owner']['login'],
                              pull_request['head']['repo']['name'])
        head_ref = pull_request['head']['sha']

        # Set policy defaults
        if head == repository:
            policy = {
                'specs': True,
                'code': True,
                'disallow-processors': [r"dump\..*"]
            }
            policy.update(pr_policy.get('local', {}))
        else:
            policy = {
                'specs': True,
                'code': False,
                'disallow-processors': [r"dump\..*"]
            }
            policy.update(pr_policy.get('remote', {}))

        # Prepare dis-allowed processors (which will be filtered out from pipelines)
        disallowed_processors = []
        for disallowed_processor in policy['disallow-processors']:
            disallowed_processors.append(re.compile(disallowed_processor))

        # Iterate over all changed files in the PR
        pull_request_files_url = '/repos/{}/pulls/{}/files'.format(repository, issue['number'])
        files = URL_GETTER.get(pull_request_files_url)

        for changed_file in files:
            fullpath = changed_file['filename']
            dirname = os.path.dirname(fullpath)
            if dirname.startswith(base_path):
                rebased_dirname = dirname[len(base_path):].lstrip('/')
                filename = os.path.basename(fullpath)

                # Find any modified pipeline specs
                if policy['specs'] and filename == 'pipeline-spec.yaml':
                    pipeline_spec = URL_GETTER.get('/repos/{}/contents/{}'.format(head, fullpath),
                                                   {'ref': head_ref})
                    pipeline_spec = codecs.decode(pipeline_spec['content'].encode('ascii'), 'base64').decode('utf8')
                    pipeline_spec = yaml.load(pipeline_spec)
                    processors = {}

                    # Fetch referenced code if needed
                    if policy['code']:
                        dir_listing = URL_GETTER.get('/repos/{}/contents/{}'.format(head, dirname),
                                                     {'ref': head_ref})
                    else:
                        dir_listing = URL_GETTER.get('/repos/{}/contents/{}'.format(repository, dirname),
                                                     {'ref': head_ref})

                    if dir_listing is not None:
                        for dir_entry in dir_listing:
                            if dir_entry['type'] == 'file' and dir_entry['name'].endswith('.py'):
                                processor_code = \
                                    URL_GETTER.get('/repos/{}/contents/{}'
                                                   .format(head, dir_entry['path']),
                                                   {'ref': head_ref})
                                processor_code = \
                                    codecs.decode(processor_code['content'].encode('ascii'), 'base64').decode('utf8')
                                processors[dir_entry['name'].rstrip('.py')] = processor_code

                    # Fix pipeline steps
                    for pipeline_id, pipeline_details in pipeline_spec.items():
                        pipeline_steps = []
                        for step in pipeline_details['pipeline']:
                            run = step['run']
                            if any(dp.fullmatch(run)
                                   for dp in disallowed_processors):
                                continue
                            if step['run'] in processors:
                                step['code'] = processors[step['run']]
                            pipeline_steps.append(step)
                        pipeline_details['pipeline'] = pipeline_steps
                        yield urljoin(rebased_dirname, pipeline_id_format), \
                            pipeline_steps

    @classmethod
    def handle_combined_issue(cls, repository, base_path, issue, issue_policy, pr_policy):
        if 'pull_request' in issue:
            # Pull Request
            if pr_policy is None:
                return

            if issue['state'] != 'open':
                return

            yield from cls.handle_pr(repository, base_path, issue, pr_policy)

        else:
            # Issue
            if issue_policy is False:
                return

            closed_issues = issue_policy.get('closed', False)
            if issue['state'] != 'open' and not closed_issues:
                return

            yield from cls.handle_issue(issue, issue_policy)

    @classmethod
    def fetch_code(cls, policy, repository, base):
        code_path = '.github.code.{}'.format(repository.replace('/', '.'))
        os.makedirs(code_path, exist_ok=True)

        # Get local code's ETag
        hashfile = os.path.join(code_path, 'etag')
        on_disk_hash = None
        if os.path.exists(hashfile):
            with open(hashfile, 'r') as on_disk_hash_file:
                on_disk_hash = on_disk_hash_file.read()

        # Get remote code's ETag
        etag = None
        check_etag_resp = requests.head('https://api.github.com/repos/{}/tarball'.format(repository), allow_redirects=True)
        if check_etag_resp.status_code == 200:
            etag = check_etag_resp.headers['ETag']

        clone_path = os.path.join(code_path, 'clone')
        os.makedirs(clone_path, exist_ok=True)

        # Update files if needed
        if etag is not None and etag != on_disk_hash:
            # Check for existing files
            existing_files = set()
            for dirpath, dirnames, filenames in os.walk(clone_path):
                for filename in filenames:
                    existing_files.add(os.path.join(dirpath, filename))

            ref = policy.get('ref', 'master')
            tarball_resp = requests.get('https://api.github.com/repos/{}/tarball/{}'.format(repository, ref),
                                        allow_redirects=True, stream=True)
            tarball = tarfile.open(fileobj=tarball_resp.raw, mode='r|gz')

            while True:
                member = tarball.next()
                if member is None:
                    break
                if not member.isfile():
                    continue
                name = member.name
                name = '/'.join(name.split('/')[1:])  # Remove first part of path
                if name.startswith(base):
                    name = name[len(base):].lstrip('/')
                    fullpath = os.path.join(clone_path, name)
                    os.makedirs(os.path.dirname(fullpath), exist_ok=True)

                    with open(fullpath, 'wb') as outfile:
                        shutil.copyfileobj(tarball.extractfile(member), outfile)
                    if fullpath in existing_files:
                        existing_files.remove(fullpath)

            # Delete obsolete files
            for to_delete in existing_files:
                os.unlink(to_delete)

            # Save ETag for future checks
            with open(hashfile, 'w') as on_disk_hash_file:
                on_disk_hash_file.write(etag)

        for dirpath, dirnames, filenames in os.walk(clone_path):
            for filename in filenames:
                fullpath = os.path.join(dirpath, filename)
                basepath = dirpath[len(clone_path):].lstrip('/')
                if filename == 'pipeline-spec.yaml':
                    with open(fullpath) as pipeline_spec_file:
                        pipeline_spec = yaml.load(pipeline_spec_file)
                        for pipeline_id, pipeline_details in pipeline_spec.items():
                            pipeline_details['__path'] = dirpath
                            yield os.path.join(basepath, 'gh-'+pipeline_id), pipeline_details


    @classmethod
    def generate_pipeline(cls, source):
        for pipeline_id_prefix, defs in source.items():
            repository = defs['repository']
            base_path = defs.get('base-path', 'pipelines/')

            # issues
            issue_policy = defs.get('issues', {})

            # pull requests
            pr_policy = defs.get('pull-requests')

            # code
            code_policy = defs.get('code')

            if code_policy is not None:
                yield from cls.fetch_code(code_policy, repository, base_path)

            issues_url = '/repos/{}/issues'.format(repository)
            issues = URL_GETTER.get(issues_url)

            if issues is not None:
                for issue in issues:
                    for pipeline_id_format, pipeline_steps in \
                            cls.handle_combined_issue(repository, base_path, issue, issue_policy, pr_policy):

                        title_slug = slugify(issue['title'])
                        fmt = {
                            'issue-id': issue['number'],
                            'title-slug': title_slug
                        }
                        pipeline_id = pipeline_id_format.format(**fmt)
                        pipeline_id = urljoin(pipeline_id_prefix, pipeline_id)
                        pipeline_details = {
                            'title': issue['title'],
                            'pipeline': pipeline_steps
                        }
                        if issue.get('body') is not None:
                            pipeline_details['description'] = issue['body']
                        yield pipeline_id, pipeline_details
