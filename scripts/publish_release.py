#!/usr/bin/env python3
"""Create a tagged GitHub Release using GitHub's source archives."""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


class PublishError(RuntimeError):
    """A Release cannot be published for the validated tag commit."""


class GitHubClient:
    def __init__(self, token):
        self.token = token

    def api(self, method, path, *, payload=None, allow_missing=False):
        request = urllib.request.Request(
            f"https://api.github.com{path}",
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "sdk-skills-release-publisher",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if allow_missing and error.code == 404:
                return None
            raise PublishError(f"GitHub API {method} {path} failed ({error.code})") from error
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise PublishError(f"GitHub API {method} {path} failed: {error}") from error


def resolve_tag_commit(client, repo, tag):
    ref = client.api("GET", f"/repos/{repo}/git/ref/tags/{urllib.parse.quote(tag, safe='')}", allow_missing=True)
    if ref is None:
        raise PublishError(f"remote tag does not exist: {tag}")
    obj = ref.get("object", {})
    seen = set()
    while obj.get("type") == "tag":
        sha = obj.get("sha")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha) or sha in seen:
            raise PublishError(f"invalid annotated tag chain for {tag}")
        seen.add(sha)
        obj = client.api("GET", f"/repos/{repo}/git/tags/{sha}").get("object", {})
    sha = obj.get("sha")
    if obj.get("type") != "commit" or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise PublishError(f"tag {tag} does not resolve to a commit")
    return sha


def identity_header(tag, commit):
    return f"<!-- sdk-skills-release\ntag: {tag}\ncommit: {commit}\n-->\n"


def publish_release(client, repo, tag, commit):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise PublishError("--repo must be in owner/repository form")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9][a-zA-Z0-9.-]*)?", tag):
        raise PublishError("--tag must be vX.Y.Z or vX.Y.Z-prerelease")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise PublishError("--commit must be a full lowercase commit SHA")
    if resolve_tag_commit(client, repo, tag) != commit:
        raise PublishError(f"remote tag {tag} differs from the validated commit")
    header = identity_header(tag, commit)
    prerelease = "-" in tag
    release = client.api("GET", f"/repos/{repo}/releases/tags/{tag}", allow_missing=True)
    created = release is None
    if created:
        release = client.api("POST", f"/repos/{repo}/releases", payload={
            "tag_name": tag, "target_commitish": commit, "name": f"SDK Skills {tag}",
            "body": header + f"# SDK Skills {tag}\n\nCommit: `{commit}`\n\n"
                    "Download Source code (zip) or Source code (tar.gz), extract it, "
                    "and run `bash install.sh` from the extracted directory. "
                    "See README.md and CHANGELOG.md for installation options and changes.\n",
            "draft": True, "prerelease": prerelease,
        })
    if (release.get("tag_name") != tag
            or not isinstance(release.get("body"), str) or not release["body"].startswith(header)
            or release.get("prerelease") is not prerelease):
        raise PublishError("existing release belongs to a different snapshot or release type")
    if type(release.get("id")) is not int or type(release.get("draft")) is not bool:
        raise PublishError("GitHub returned an invalid release")
    # Recheck before publishing; an interrupted draft can be resumed for this exact commit.
    if resolve_tag_commit(client, repo, tag) != commit:
        raise PublishError(f"remote tag {tag} changed while preparing the release")
    if release["draft"]:
        release = client.api("PATCH", f"/repos/{repo}/releases/{release['id']}", payload={"draft": False})
        if release.get("draft") is not False:
            raise PublishError("GitHub did not publish the release")
    print(f"Release {tag} {'created' if created else 'verified'} at commit {commit}; source archives provided by GitHub")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="GitHub owner/repository")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise PublishError("GITHUB_TOKEN is required")
    publish_release(GitHubClient(token), args.repo, args.tag, args.commit)


if __name__ == "__main__":
    try:
        main()
    except PublishError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
