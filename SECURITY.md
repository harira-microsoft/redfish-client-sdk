<!-- BEGIN MICROSOFT SECURITY.MD V0.0.9 BLOCK -->

## Security

Microsoft takes the security of our software products and services seriously, which includes all source code repositories managed through our GitHub organizations.

If you believe you have found a security vulnerability in any Microsoft-owned repository that meets [Microsoft's definition of a security vulnerability](https://aka.ms/security.md/definition), please report it to us as described below.

## Reporting Security Issues

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them to the Microsoft Security Response Center (MSRC) at [https://msrc.microsoft.com/create-report](https://aka.ms/security.md/msrc/create-report).

You should receive a response within 24 hours. If for some reason you do not, please follow up via the messaging functionality at the bottom of the Activity tab on your vulnerability report at [https://msrc.microsoft.com/report/vulnerability](https://msrc.microsoft.com/report/vulnerability/).

Please include the following information to help us better understand the nature and scope of the possible issue:

- Type of issue (e.g. credential exposure, memory safety, injection, etc.)
- Full paths of source file(s) related to the manifestation of the issue
- The location of the affected source code (tag/branch/commit or direct URL)
- Any special configuration required to reproduce the issue
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

This information will help us triage your report more quickly.

## Preferred Languages

We prefer all communications to be in English.

## Policy

Microsoft follows the principle of [Coordinated Vulnerability Disclosure](https://aka.ms/security.md/cvd).

<!-- END MICROSOFT SECURITY.MD V0.0.9 BLOCK -->

---

## SDK-Specific Security Notes

This SDK handles authentication credentials (username/password, session tokens) and TLS connections to BMC endpoints. When reporting issues please pay particular attention to:

- Credential exposure in logs or error messages
- TLS certificate validation bypasses
- Session token leakage across requests
- Memory safety issues in the C++ or Rust transport layer
