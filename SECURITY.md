# Security policy

## Reporting a vulnerability

Please do not report security problems in public issues, pull requests or
discussions.

Email **[github@glassflow.dev](mailto:github@glassflow.dev)** with:

- what the problem is and where it is (file, registry row, tool);
- how it can be reproduced, or the recording or span that shows it;
- what an attacker could do with it, or what data could be exposed.

We will acknowledge your report and keep you informed while we investigate
and fix it. Once a fix is released we are happy to credit you, unless you
prefer to stay anonymous.

## What counts

This repository runs nothing in production: it is data, generators and
tooling whose output the Rius SDKs and the Rius backend vendor. The problems
that matter most are therefore in the data itself, for example:

- a key that carries prompt, completion or other user content but is missing
  from the content allowlist (`registry/allowlists.yaml`), so it would leave a
  process with content capture turned off;
- a key on the pending-snapshot allowlist that can carry content;
- a `process_local` attribute that would be exported;
- a recording under `fixtures/` that contains a secret, a credential or
  personal data;
- a generator or tool that could be made to execute untrusted input.

A vulnerability in a Rius SDK itself belongs to that SDK's repository, but if
you are unsure where it belongs, send it to the address above and we will
route it.

## Supported versions

Only the latest release of the registry receives fixes. Consumers pin a
version, so a fix reaches them when they move their pin.
