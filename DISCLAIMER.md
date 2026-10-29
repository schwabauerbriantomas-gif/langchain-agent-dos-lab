# Disclaimer

This repository contains **proof-of-concept denial-of-service techniques** against a
locally deployed AI-agent application. It is published for **defensive security
research**: to help developers and operators understand how the default
persistence pattern of LangChain/LangGraph agents behaves when message size is
attacker-controlled, and to justify specific mitigations.

- **Authorized use only.** Run this only against systems you own or have explicit
  written permission to test. Using these techniques against third-party systems is
  illegal in most jurisdictions and explicitly not condoned.
- **Lab conditions.** All measurements were taken on a loopback victim on the
  author's own machine. Numbers may differ on other versions, configurations,
  checkpointer backends, or models.
- **No vulnerability claim.** This is a design-level resource-exhaustion risk in a
  default deployment pattern, not a claimed CVE. Vendors may reasonably classify it
  as "works as designed / hardening needed"; the mitigations section of the README
  is written for exactly that audience.
- **No warranty.** The code is provided as-is under the MIT license.
