# Releasing

Releases are cut from a git tag. Pushing a tag `vX.Y.Z` triggers
`.github/workflows/release.yml`, which verifies the tag, runs the tests, builds the
package, and creates a GitHub Release. Optionally it then publishes the same files to PyPI.

## Versioning policy (SemVer)

The version lives in `pyproject.toml` (`project.version`) and follows
[Semantic Versioning](https://semver.org). The public interface is the command line
(`balance-the-loan-books <dataset_dir>`: expected input files and columns, output files and
columns, exit codes, flags) and the documented Python API in `balance_the_loan_books`.

- MAJOR: breaking change to input or output file names or columns, assignment or yield
  semantics, exit codes, removed flags or public functions, or dropping a supported Python
  version.
- MINOR: backwards-compatible features, such as new options, new optional columns, or new
  public functions.
- PATCH: backwards-compatible bug fixes, docs, and internal changes.

Before 1.0.0, minor bumps may include breaking changes.

Pre-releases use PEP 440 suffixes, written in the normalized form: `1.0.0rc1`,
`1.0.0b1`, `1.0.0a1`. Tag them `v1.0.0rc1`. The form `v1.0.0-rc.1` is rejected, because uv
normalizes it to `1.0.0rc1` and the tag must equal `v` plus the project version. Pre-releases
are marked as pre-releases on GitHub.

## Release steps

1. Open a version-bump PR. Start from an up-to-date `main`:

   ```sh
   git switch -c release-vX.Y.Z
   uv version --bump patch   # or minor / major; updates pyproject.toml and uv.lock
   uv version --short        # prints the new version
   git commit -am "Release vX.Y.Z"
   ```

   For a pre-release: `uv version 1.0.0rc1`.
2. Merge that PR first, and make sure CI is green on `main`. Never tag an unmerged commit.
3. Pull `main` and confirm the version:

   ```sh
   git switch main && git pull
   uv version --short        # must print X.Y.Z
   ```
4. Tag and push:

   ```sh
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin vX.Y.Z
   ```
5. Watch the Release workflow (Actions tab, or `gh run watch`). It fails early if the tag is
   not semver or does not equal `v` plus the project version.

The workflow can also be run manually (Actions, Release, Run workflow) with the name of an
existing tag.

## What the workflow does

1. Checks out the tag and installs locked dependencies; Python comes from `.python-version`.
2. Fails if the tag is not `vMAJOR.MINOR.PATCH[aN|bN|rcN]` or differs from `v` + `uv version --short`.
3. Runs the test suite, then `uv build` (sdist and wheel).
4. Uploads `dist/` as a workflow artifact and creates a GitHub Release with generated notes and
   the dist files attached.
5. If the repository variable `PUBLISH_TO_PYPI` is `true`: the `publish-pypi` job downloads that
   same artifact and runs `uv publish --trusted-publishing always`. Nothing is rebuilt.

## Publishing to PyPI (one-time setup)

Check that the name `balance-the-loan-books` is still available on PyPI before the first upload. Publishing uses Trusted Publishing (OIDC), so no API token is stored.

1. Create a PyPI account at https://pypi.org and enable 2FA.
2. Add a pending trusted publisher at https://pypi.org/manage/account/publishing/ with: PyPI
   project name `balance-the-loan-books`, owner `evonnec`, repository
   `balance-the-loan-books`, workflow `release.yml`, environment `pypi`. The first
   successful publish creates the project.
3. In the GitHub repo, Settings, Environments, create an environment named `pypi`.
   Optionally require reviewer approval, so each publish waits for a manual approval.
4. Enable the job:

   ```sh
   gh variable set PUBLISH_TO_PYPI --body true
   ```

5. Make sure project metadata in `pyproject.toml` (description, readme, authors, URLs,
   license) is complete before the first upload.

Optional dry run: register a pending publisher at https://test.pypi.org with the same values,
and publish a pre-release manually with `uv publish --publish-url https://test.pypi.org/legacy/`
from a trusted environment. The workflow itself targets PyPI only.

To stop publishing, delete the variable: `gh variable delete PUBLISH_TO_PYPI`.

## Recovering from a bad tag

If the Release workflow failed, or the tag points at the wrong commit, and nothing reached PyPI:

```sh
git tag -d vX.Y.Z
git push origin :refs/tags/vX.Y.Z
gh release delete vX.Y.Z --yes   # only if a GitHub Release was created
```

Fix the problem on `main` through a PR, then tag again from step 3 above.

PyPI versions are immutable: a filename can never be re-uploaded, even after deletion. If
`X.Y.Z` reached PyPI with a defect, do not reuse the number. Fix forward with a new patch
version, and yank the bad release on PyPI if needed.

## Installing a released wheel

```sh
uv tool install https://github.com/evonnec/balance-the-loan-books/releases/download/vX.Y.Z/balance_the_loan_books-X.Y.Z-py3-none-any.whl
balance-the-loan-books <dataset_dir>
```

Once published to PyPI: `uv tool install balance-the-loan-books`.
