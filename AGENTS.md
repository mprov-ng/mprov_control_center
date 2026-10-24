<!-- OPENWIKI:START -->

## OpenWiki

This repository uses OpenWiki for recurring code documentation. Start with `openwiki/quickstart.md`, then follow its links to architecture, workflows, domain concepts, operations, integrations, testing guidance, and source maps.

The wiki is refreshed by periodically running `openwiki code --update` in this repo. Do not hand-edit generated OpenWiki pages unless explicitly asked; prefer updating source code/docs and letting OpenWiki regenerate.

<!-- OPENWIKI:END -->

# Working in the mprov-ng repos

Instructions for AI coding agents (and anyone else) working in the mprov-ng
repos: mprov_control_center (the mPCC), mprov_jobserver, mprov_scripts and
mash. The same rules are kept in each of them.

## Branches

Cut every new branch from a freshly fetched default branch (`main` or
`master`), never from whatever branch is checked out:

```
git fetch origin
git switch --no-track -c <name> origin/main
```

`--no-track` stops a bare `git push` from going to the default branch. If
uncommitted changes belong on the new branch, carry them over with `git stash`
or a worktree, and leave other branches alone.

## Commits

Every commit an AI agent makes ends with an `Assisted-By` trailer naming the
model in use, instead of `Co-Authored-By`:

```
Assisted-By: <model name> <noreply@anthropic.com>
```

Add it to every commit, small or chore ones included. Don't rewrite pushed
commits to change the trailer unless asked. A maintainer's `Signed-off-by`
line may be added by their own git hook, so don't pass `-s` or add it by hand.

## Pushing

Before any `git push`, show the maintainer the commits to be pushed (hashes
and a summary of the diff) and wait for an explicit go-ahead. That covers:

- the first push of a new branch, even when a PR was asked for in general terms;
- follow-up commits on a branch that already has an open PR;
- force-pushes after a rebase, even when the content is unchanged (the hashes change);
- editing a PR description to match work that isn't pushed yet.

An approval covers the commits that were shown, not later ones.

## The mPCC REST API is a contract between repos

The mPCC's REST API is used by the other repos:

- **mprov_jobserver**, the main consumer. Plugins are under
  `src/mprov_jobserver/plugins/`; session setup is in `app.py` and `script.py`.
- **mprov_scripts**, the node scripts (e.g. `post-boot/setupBMC.py`,
  `post-boot/register_IPv6_ll.py`, `image-gen/run_ansible.sh`).
- **mash**, the CLI, and **mprov_boot**.
- The mPCC's own node-side scripts in `static/` (the stateful installer,
  `genNetworkInterfaces.py`, `mprov_boot_init.sh`).

Before changing an endpoint (reply shape, nesting depth, status codes such as
`200 []` vs `404`, required fields, content types, authentication or
permissions), check how these clients use it. If a repo isn't checked out,
clone it read-only into a scratch directory and grep it for the endpoint. Keep
the behaviour clients depend on, or say that both sides have to change
together, and in what order. Say in the PR that the change needs checking
against the client code.

The reverse applies too: when changing a client, check what the mPCC endpoint
actually returns.

## New work goes in GitHub issues

Record every new bug, follow-up or design item as a GitHub issue in the repo
it belongs to. Link related issues to each other, and to the PR or issue where
the problem was found. Show the maintainer a draft first unless they've asked
for the issue to be opened.

Fix issues on branches from the default branch, and open PRs that reference
them. In mprov_control_center, `REVIEW-2026-10.md` only keeps the items
already in it; new findings don't go there.

## Watch PRs that something depends on

When a PR is opened, or is waiting on review, and some note or follow-up has
to change once it merges, start a background watch on it straight away: poll
`gh pr view <n> --json state,mergedAt,mergeCommit` every couple of minutes
until the state is `MERGED` or `CLOSED`. Don't poll by hand in the foreground.

When it merges, update what depends on it (recording the merge commit) and
tell the maintainer. If it was closed without merging, tell them and ask
before changing anything.
