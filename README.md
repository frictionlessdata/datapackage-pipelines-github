# datapackage-pipelines-github

Extension for `datapackage-pipelines` for pulling GitHub issues of a repository and embedding them as 'failed' pipelines.

## Source spec

Place files named `github.source-spec.yaml` in your pipelines directory.
Each one should be of the form:
```yaml
<pipeline-id-prefix>:
    repository: <owner/repo>
    pull-requests: <boolean, should fetch prs? default is no>
    closed: <boolean, should fetch closed issues? default is no>
    pipeline-id-format: <string, see below>
```

`pipeline-id-format` is a Python format string with two placeholders:
- `issue-id`: The issue number 
- `title-slug`: The issue title slug

The default format is "{issue-id:03}_{title-slug}"

#### Example:
```yaml
dpp-github/issues:
    repository: firctionlessdata/datapackage-pipelines-github
    pull-requests: no
    closed: no
    pipeline-id-format: "{title-slug}__{issue-id}"
```


