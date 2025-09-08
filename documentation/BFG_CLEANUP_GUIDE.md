# BFG Repo-Cleaner: Removing Sensitive Data from Your Git Repository

BFG Repo-Cleaner is a fast, open-source tool for removing passwords, credentials, and other sensitive data from Git history. It’s much faster and simpler than git-filter-branch.

---

## 1. Prepare Your Repo

Clone a fresh copy of your repo as a bare repository (recommended):

```sh
git clone --mirror https://github.com/your/repo.git
cd repo.git
```

Or, if you’re working locally, you can use your existing repo.

---

## 2. Remove Sensitive Files

To delete all files named, for example, `*.json` (like credentials):

```sh
bfg --delete-files '*.json'
```

You can also delete folders:

```sh
bfg --delete-folders 'credentials'
```

---

## 3. Remove Passwords or Secrets from File Contents

Create a text file (e.g., `expressions.txt`) listing sensitive strings or regex patterns:

```
password
secret
regex:\bAKIA[0-9A-Z]{16}\b
```

Run BFG to replace these strings:

```sh
bfg --replace-text expressions.txt
```

By default, matches are replaced with `***REMOVED***`. You can specify custom replacements using `==>` in your expressions file.

---

## 4. Remove Large Files

To strip blobs larger than 10MB:

```sh
bfg --strip-blobs-bigger-than 10M
```

---

## 5. Clean Up and Finalize

After running BFG, run these commands to clean up your repo:

```sh
git reflog expire --expire=now --all && git gc --prune=now --aggressive
```

---

## 6. Push Changes

Force-push your cleaned history (be careful—this rewrites history):

```sh
git push --force
```

---

## 7. Additional Tips

- Always back up your repo before running BFG.
- Notify collaborators—they’ll need to re-clone after history rewrite.
- BFG only cleans history; make sure sensitive data isn’t in your latest commit.

---

## References

- [BFG Repo-Cleaner Documentation](https://rtyley.github.io/bfg-repo-cleaner/)
- [GitHub Help: Removing sensitive data](https://help.github.com/en/github/authenticating-to-github/removing-sensitive-data-from-a-repository)
