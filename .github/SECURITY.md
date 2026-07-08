# Security Policy

Python Security Response Team (PSRT) members balance security work against many
other responsibilities. Please be thoughtful about the time and attention your
report requires. Repeated failure to respect this will result in future reports
being rejected, or the reporter being banned from the `python` GitHub organization,
regardless of technical merit.

## Reporting a Vulnerability

Please use [GitHub Security Advisories](https://github.com/python/pymanager/security/advisories) to report potential issues to this project.

Alternatively, follow [the main security page](https://www.python.org/dev/security/) for alternate ways to report,
bearing in mind that eventually we will create a report using GHSA if needed.

Reports should be a few sentences describing the vulnerability. Ideally include
a proof-of-concept script that reproduces the issue and provides a clear
indication of whether the vulnerability is still present. Reports must be
plain-text only, including attachments. No PDFs, binaries, notebooks, or other
files that cannot be safely reviewed. If your proof-of-concept depends on a
specially constructed binary file, please include a script to construct it
rather than the file itself. Ideally, include a minimal patch with the mitigation
for the report.

Reports that do not contain a potential security vulnerability (such as spam or
requesting compliance or due-diligence work) will be discarded without a reply.

## Threat Model

Our threat model for the Python install manager makes the following assumptions:

* users are using the default index from python.org
* TLS/HTTPS connections are secure and are not intercepted or tampered with
* users are using the default configured directory structure
* users are running with a reasonable privilege level for their environment
* all reconfigured settings are intentional, including environment variables
* all configuration from outside of the install manager is intentional
* our code-signing infrastructure is not compromised

Any reported vulnerability that requires any of these assumptions to be broken will be closed and treated as a regular bug or a non-issue.

Notably, an index is considered to include a trustworthy set of install instructions,
and so can arbitrarily modify a user's machine by design.
Once a user is installing from a non-default feed,
whether through modified configuration (file or environment variable) or intercepted network traffic,
we cannot treat issues arising from the contents of that feed as security critical.
