# datapackage-pipelines-github

Extension for `datapackage-pipelines` for pulling stuff from GitHub.
- **Pipelines and Processor Code** from a specific branch will be pulled 
- **Issues** will be presented, using their title and description, as 'unable to start' pipelines.
- **Pull Requests** will be shown and executed, based on a predefined policies defining:
  - Should pipeline specs be pulled from PRs
  - Should processor code be pulled from PRs
  - Which processors are allowed to run, when executing PRs
  
  You can define separate policies for local PRs (from the same fork) or remote PRs (from another fork.)

note: When pulling code from PRs, we will only bring processors referenced from the 
pipeline spec and residing in the same directory as the `pipeline-spec.yaml` file. 
 
## Source spec

Place files named `github.source-spec.yaml` in your pipelines directory.
Each one should be of the form:
```yaml
<pipeline-id-prefix>:
    repository: <owner/repo>
    base-path: <where to look for pipelines and code. default is 'pipelines/'>
    code: <if not present, won't fetch code. set to {} to use the defaults>
      ref: <which branch/commit to use to get code from. default is 'master>
    issues: <if not present, won't fetch issues. set to {} to use the defaults>
      closed: <boolean, should fetch closed issues? default is no>
      pipeline-id-format: <string, see below>    
    pull-requests: <if not present, won't fetch prs. set to {} to use the defaults>
      local: <policy for local PRs> 
        specs: <boolean, should pull pipeline specs? default is yes> 
        code: <boolean, should pull code from PRs? default is yes>
        disallow-processors: <which processors are not allowed to run in PRs? default is ["dump\..*"]>
         - <regular-expression for processor name>
      remote: <policy for remote PRs, same as local>
        specs: <boolean, should pull pipeline specs? default is yes> 
        code: <boolean, should pull code from PRs? default is no>
        disallow-processors: <which processors are not allowed to run in PRs? default is ["dump\..*"]>
         - <regular-expression for processor name>
      pipeline-id-format: <string, see below>
```

`pipeline-id-format` is a Python format string with two placeholders:
- `issue-id`: The issue/pr number 
- `title-slug`: The issue title slug

The default format for issues is "issue/{issue-id:03}_{title-slug}"
The default format for pull-requests is "pr/{pr-id:03}_{title-slug}"

#### Example:
```yaml
dpp-github:
    repository: firctionlessdata/datapackage-pipelines-github
    code:
      ref: master
    pull-requests:
      local:
        specs: yes
        code: yes
        disallow-processors:
         - "dump\..*"
      remote:
        specs: no    
      pipeline-id-format: "{title-slug}__{issue-id}"
    issues:
      closed: no
      pipeline-id-format: "{title-slug}__{issue-id}"
```


