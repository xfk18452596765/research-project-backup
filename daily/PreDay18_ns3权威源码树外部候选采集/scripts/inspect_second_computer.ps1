# Run read-only: git branch -a; git reflog show --all; git fsck --full --unreachable --no-reflogs; git fsck --lost-found; git stash list.
# Do not run git gc, git prune, git clean, configure, build, or tests. Export only manifests and SHA logs.
