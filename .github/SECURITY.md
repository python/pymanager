# Security Policy

## Reporting a Vulnerability

Please use [GitHub Security Advisories](https://github.com/python/pymanager/security/advisories) to report potential issues to this project.

Alternatively, follow [the main security page](https://www.python.org/dev/security/) for alternate ways to report,
bearing in mind that eventually we will create a report using GHSA if needed.

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
