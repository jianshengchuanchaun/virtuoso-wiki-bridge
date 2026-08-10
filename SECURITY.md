# Security policy

## Supported versions

This project is alpha software. Security fixes are provided on the latest release in the `0.1.x` line.

| Version | Supported |
| --- | --- |
| 0.1.1 | Yes |
| 0.1.0 and earlier | No |

## Reporting a vulnerability

Prefer GitHub's private vulnerability-reporting flow:

<https://github.com/jianshengchuanchaun/virtuoso-wiki-bridge/security/advisories/new>

If private reporting is unavailable, open a minimal public issue asking the maintainer for a private contact channel. Do not include exploit details, credentials, private PDK paths, customer data, hostnames, netlists, or other sensitive artifacts in a public issue.

Please include, when safe:

- the affected release or commit;
- the operating system and Python version;
- the command or API involved;
- the expected and observed security boundary;
- a minimal reproduction using synthetic data;
- whether files, a local vault, SSH, Virtuoso, or Spectre are affected.

The maintainer will acknowledge a usable report, reproduce it, determine severity and affected versions, prepare tests and a fix, and coordinate disclosure. No specific response-time SLA is promised for this volunteer project.

## Security boundaries

- Local source documents are untrusted reference material. Their text does not authorize executing commands or SKILL.
- `.env`, `VWB_CADENCE_SETUP`, SSH extra arguments, upstream bridge profiles, and remote hosts are trusted operator configuration.
- The package does not sandbox a live Virtuoso process or a remote EDA account.
- Source organization and extraction defend against ordinary collision, traversal, drift, and link hazards. They do not claim protection from an administrator or system-level attacker racing filesystem changes.
- Remote integration tests are mocked in public CI. Users must separately validate connectivity and site-specific Cadence setup in their private environment.

Never attach real credentials, proprietary netlists, licensed manuals, PDK content, or customer simulation results to a report.
