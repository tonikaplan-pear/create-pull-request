#!/usr/bin/env python3
''' Create Pull Request '''
import json
import os
import random
import string
import sys
import time
from git import Repo
from github import Github


def get_github_event(github_event_path):
    with open(github_event_path) as f:
        github_event = json.load(f)
    if bool(os.environ.get('DEBUG_EVENT')):
        print(os.environ['GITHUB_EVENT_NAME'])
        print(json.dumps(github_event, sort_keys=True, indent=2))
    return github_event


def ignore_event(event_name, event_data):
    if event_name == "push":
        ref = "{ref}".format(**event_data)
        if not ref.startswith('refs/heads/'):
            print("Ignoring events for tags and remotes.")
            return True
    return False


def get_head_short_sha1(repo):
    return repo.git.rev_parse('--short', 'HEAD')


def get_random_suffix(size=7, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def remote_branch_exists(repo, branch):
    for ref in repo.remotes.origin.refs:
        if ref.name == ("origin/%s" % branch):
            return True
    return False


def get_author_default(event_name, event_data):
    if event_name == "push":
        email = "{head_commit[author][email]}".format(**event_data)
        name = "{head_commit[author][name]}".format(**event_data)
    else:
        email = os.environ['GITHUB_ACTOR'] + '@users.noreply.github.com'
        name = os.environ['GITHUB_ACTOR']
    return email, name


def set_git_config(git, email, name):
    git.config('--global', 'user.email', '"%s"' % email)
    git.config('--global', 'user.name', '"%s"' % name)


def set_git_remote_url(git, token, github_repository):
    git.remote(
        'set-url', 'origin', "https://x-access-token:%s@github.com/%s" %
        (token, github_repository))


def checkout_branch(git, remote_exists, branch):
    if remote_exists:
        print(" ---- exists")
        git.stash('--include-untracked')
        git.checkout(branch)
        try:
            git.stash('pop')
        except BaseException:
            print(" ----err")
            git.checkout('--theirs', '.')
            git.reset()
    else:
        print(" ---- doesnt exist")
        git.checkout('HEAD', b=branch)


def push_changes(git, branch, commit_message):
    git.add('-A')
    git.commit(m=commit_message)
    return git.push('-f', '--set-upstream', 'origin', branch)


def cs_string_to_list(str):
    # Split the comma separated string into a list
    l = [i.strip() for i in str.split(',')]
    # Remove empty strings
    return list(filter(None, l))


def process_event(event_name, event_data, repo, branch, base, remote_exists):
    # Fetch required environment variables
    github_token = os.environ['GITHUB_TOKEN']
    github_repository = os.environ['GITHUB_REPOSITORY']
    # Fetch optional environment variables with default values
    commit_message = os.getenv(
        'COMMIT_MESSAGE',
        "Auto-committed changes by create-pull-request action")
    title = os.getenv(
        'PULL_REQUEST_TITLE',
        "Auto-generated by create-pull-request action")
    body = os.getenv(
        'PULL_REQUEST_BODY', "Auto-generated pull request by "
        "[create-pull-request](https://github.com/peter-evans/create-pull-request) GitHub Action")
    # Fetch optional environment variables with no default values
    pull_request_labels = os.environ.get('PULL_REQUEST_LABELS')
    pull_request_assignees = os.environ.get('PULL_REQUEST_ASSIGNEES')
    pull_request_milestone = os.environ.get('PULL_REQUEST_MILESTONE')
    pull_request_reviewers = os.environ.get('PULL_REQUEST_REVIEWERS')
    pull_request_team_reviewers = os.environ.get('PULL_REQUEST_TEAM_REVIEWERS')

    # Update URL for the 'origin' remote
    set_git_remote_url(repo.git, github_token, github_repository)

    # If the remote existed then we are using fixed branch strategy.
    # A PR should already exist and we can finish here.
    if remote_exists:
        print("Updated pull request branch %s." % branch)
        sys.exit()

    # Create the pull request
    print("Creating a request to pull %s into %s." % (branch, base))
    print("title %s body %s branch %s base %s" % (title, body, branch, base))
    github_repo = Github(github_token).get_repo(github_repository)
    pull_request = github_repo.create_pull(
        title=title,
        body=body,
        base=base,
        head=branch)
    print("Created pull request %d." % pull_request.number)
    os.system(
        'echo ::set-env name=PULL_REQUEST_NUMBER::%d' %
        pull_request.number)

    # Set labels, assignees and milestone
    if pull_request_labels is not None:
        print("Applying labels")
        pull_request.as_issue().edit(labels=cs_string_to_list(pull_request_labels))
    if pull_request_assignees is not None:
        print("Applying assignees")
        pull_request.as_issue().edit(assignees=cs_string_to_list(pull_request_assignees))
    if pull_request_milestone is not None:
        print("Applying milestone")
        milestone = github_repo.get_milestone(int(pull_request_milestone))
        pull_request.as_issue().edit(milestone=milestone)

    # Set pull request reviewers and team reviewers
    if pull_request_reviewers is not None:
        print("Requesting reviewers")
        pull_request.create_review_request(
            reviewers=cs_string_to_list(pull_request_reviewers))
    if pull_request_team_reviewers is not None:
        print("Requesting team reviewers")
        pull_request.create_review_request(
            team_reviewers=cs_string_to_list(pull_request_team_reviewers))


# Get the JSON event data
event_name = os.environ['GITHUB_EVENT_NAME']
event_data = get_github_event(os.environ['GITHUB_EVENT_PATH'])
# Check if this event should be ignored
skip_ignore_event = bool(os.environ.get('SKIP_IGNORE'))
if skip_ignore_event or not ignore_event(event_name, event_data):
    # Set the repo to the working directory
    repo = Repo(os.getcwd())
    # Get the default for author email and name
    author_email, author_name = get_author_default(event_name, event_data)
    # Set commit author overrides
    author_email = os.getenv('COMMIT_AUTHOR_EMAIL', author_email)
    author_name = os.getenv('COMMIT_AUTHOR_NAME', author_name)
    # Set git configuration
    set_git_config(repo.git, author_email, author_name)

    # Fetch/Set the branch name
    branch_prefix = os.getenv(
        'PULL_REQUEST_BRANCH',
        'create-pull-request/patch')
    # Fetch the git ref
    github_ref = os.environ['GITHUB_REF']
    # Fetch an optional base branch override
    base_override = os.environ.get('PULL_REQUEST_BASE')

    # Set the base branch
    if base_override is not None:
        base = base_override
    #     checkout_branch(repo.git, True, base)
    elif github_ref.startswith('refs/pull/'):
        # Switch to the merging branch instead of the merge commit
        base = os.environ['GITHUB_HEAD_REF']
        repo.git.checkout(base)
    else:
        base = github_ref[11:]

    # Skip if the current branch is a PR branch created by this action.
    # This may occur when using a PAT instead of GITHUB_TOKEN.
    if base.startswith(branch_prefix):
        print("Branch '%s' was created by this action. Skipping." % base)
        sys.exit()

    # Fetch an optional environment variable to determine the branch suffix
    branch_suffix = os.getenv('BRANCH_SUFFIX', 'short-commit-hash')
    if branch_suffix == "short-commit-hash":
        # Suffix with the short SHA1 hash
        branch = "%s-%s" % (branch_prefix, get_head_short_sha1(repo))
    elif branch_suffix == "timestamp":
        # Suffix with the current timestamp
        branch = "%s-%s" % (branch_prefix, int(time.time()))
    elif branch_suffix == "random":
        # Suffix with the current timestamp
        branch = "%s-%s" % (branch_prefix, get_random_suffix())
    elif branch_suffix == "none":
        # Fixed branch name
        branch = branch_prefix
    else:
        print(
            "Branch suffix '%s' is not a valid value." %
            branch_suffix)
        sys.exit(1)

    # Check if the remote branch exists
    remote_exists = remote_branch_exists(repo, branch)

    if remote_exists:
        if branch_suffix == 'short-commit-hash':
            # A remote branch already exists for the HEAD commit
            print(
                "Pull request branch '%s' already exists for this commit. Skipping." %
                branch)
            sys.exit()
        elif branch_suffix in ['timestamp', 'random']:
            # Generated branch name clash with an existing branch
            print(
                "Pull request branch '%s' already exists. Please re-run." %
                branch)
            sys.exit(1)

    # Checkout branch
    print(
        "Checking out '%s' branch" %
        branch)
    checkout_branch(repo.git, remote_exists, branch)
    print("end early")
    # process_event(
    #     event_name,
    #     event_data,
    #     repo,
    #     branch,
    #     base,
    #     remote_exists)