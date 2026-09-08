## Summary

Explain the user-visible problem and the smallest change that solves it.

## Change type

- [ ] Runtime or bug fix
- [ ] Skill instructions or routing
- [ ] Test or CI improvement
- [ ] Documentation or packaging

## Verification

- [ ] `python -m compileall -q plugins/codex-audio-download-skills/skills scripts tests`
- [ ] `python -m unittest discover -s tests -v`
- [ ] Relevant Skill and plugin metadata validation completed
- [ ] No real platform download is required for the test

Add the exact commands and summarized results:

```text
command — result
```

## Safety and privacy

- [ ] Explicit download intent and one-video scope remain intact.
- [ ] The change does not bypass DRM, paywalls, account entitlements, or region restrictions.
- [ ] External commands use argument arrays and never interpolate user input into a shell command.
- [ ] Fixtures and screenshots are fictional, sanitized, or self-generated.
- [ ] No cookies, tokens, signed URLs, browser profiles, personal paths, downloaded media, or private titles are included.
- [ ] README and README.zh-CN.md remain consistent when user-facing behavior changes.

## Release note

Write one concise line for users, or enter `Not user-facing`.
