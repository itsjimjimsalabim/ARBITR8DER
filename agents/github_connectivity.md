# GitHub Connectivity Notes

ARBITR8DER can connect to GitHub several ways. Use the working path first, then fall back only when a specific path fails.

## Working Path: HTTPS Through gh

Current Git operations are configured for HTTPS:

```powershell
git remote -v
gh auth status
git ls-remote --heads origin main
```

The GitHub CLI is authenticated as `itsjimjimsalabim`, and `gh auth setup-git` has been run. This is the practical default for push, pull, issue, and PR work.

Keep the PAT only in local ignored key storage:

```text
agents/KEYS
```

Do not paste full PATs into tracked docs, prompts, scripts, or commits.

## Optional Path: SSH

SSH is separate from PAT authentication. A GitHub account SSH key works only when this machine has the matching private key and the SSH client offers it.

Current observed state:

- GitHub account key reference: `itsjimjimsalabim_key`
- GitHub account key fingerprint: `SHA256:PAQfiRWlqUXMisrEl1leaHOWmFP904scntu5bus/hjI`
- Local private key observed in `C:\Users\itsji\.ssh`: `oracle_core_20260709.key`
- Local private key fingerprint: `SHA256:0aCVhSRMtGFNtF+p0Ff6Zpa9AgJzKr3RPWUj4g5zoKg`

Those fingerprints do not match. GitHub rejects the local Oracle key, and the matching private key for `itsjimjimsalabim_key` has not been found locally.

Useful checks:

```powershell
ssh -T git@github.com
ssh -vvv -T git@github.com
ssh-keygen -lf C:\Users\itsji\.ssh\some_key.pub -E sha256
ssh -i C:\Users\itsji\.ssh\some_private_key -o IdentitiesOnly=yes -T git@github.com
```

To make SSH work, either find the private key whose public-key fingerprint is `SHA256:PAQfiRWlqUXMisrEl1leaHOWmFP904scntu5bus/hjI`, or generate a fresh local SSH key and add its `.pub` value to GitHub.

## GitHub MCP

GitHub MCP is useful for richer GitHub work: issues, PRs, review comments, checks, and repository metadata. It is not required for basic Git push/pull because HTTPS through `gh` already works.

If GitHub MCP is connected, use the same local-secret rule: tokens live only in ignored key stores, environment variables, OS keyring, or the MCP connector's secure storage. Never commit them.

## Why gh ssh-key list Returns 403

`gh ssh-key list` calls GitHub's authenticated SSH-key API. Repository read/write permission is not enough for that endpoint.

For a fine-grained PAT, GitHub requires user-level `Git SSH keys` permission:

- Read permission to list or get SSH keys.
- Write permission to create or delete SSH keys.

SSH signing keys are a different GitHub permission named `SSH signing keys`.

Fix options:

1. Edit or recreate the fine-grained PAT with user-level `Git SSH keys: Read` if the only goal is to run `gh ssh-key list`.
2. Use `Git SSH keys: Write` only if the token must add or remove account SSH keys through the API.
3. Keep the current PAT unchanged if repo push/pull is the only required operation.
4. Use the GitHub web UI to inspect or add SSH keys instead of granting token access to account SSH-key management.

Do not rotate, revoke, delete, or deprecate keys just to fix this 403. The 403 means the token lacks that specific user-level permission, not that repo HTTPS access is broken.
