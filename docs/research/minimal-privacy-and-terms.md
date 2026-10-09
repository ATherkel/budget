---
type: research
---
# Minimal privacy notice and personal-use terms

Researched 2026-10-09 for issue #248. Scope: a personally operated Budget
installation and the owner's restricted Enable Banking application. These are
drafting choices, not a finding that any deployment meets all legal requirements.

## Template selection and reuse

The Danish Data Protection Agency's [small-business privacy guide](https://www.datatilsynet.dk/regler-og-vejledning/gdpr-univers-for-smaa-virksomheder/trin-4-oplys-om-at-du-behandler-personoplysninger)
provides a privacy-policy example and a useful short checklist: identity and
contact, data categories, purposes and legal basis, recipients, retention, and
rights. Use these topics as a drafting checklist in original wording, adapted
to this installation; do not import the example business's practices.

[Automattic's Legalmattic](https://github.com/Automattic/legalmattic) publishes
reusable privacy and terms documents under CC BY-SA 4.0. Its
[terms](https://wordpress.com/tos/) separate account responsibilities,
third-party services, intellectual property, changes, and stopping use. Most
of its paid-service, content-publication, and dispute provisions do not fit this
project. Reusing its text as an adaptation requires the applicable attribution
and share-alike conditions. The recommended approach is independently written
documents informed by these general topics, without copying its clauses or
adopting its license for the repository.

## Minimum useful outlines

**Privacy notice:** identify the personal installation and operator; explain
the budgeting purpose and data actually handled; describe storage, any
recipients, retention and deletion; give a private contact route. Explain
Enable Banking separately and distinguish planned API access from features
already present. Describe backups and operator-configured services accurately;
avoid unconditional promises such as "data never leaves your computer".

**Terms and Conditions:** describe self-hosted personal use; explain that each
operator supplies their own installation and provider registration; assign
responsibility for credentials, lawful access, backups and checking results;
link the privacy notice and provider terms; distinguish these operating terms
from any software license. Do not invent a software license, commercial service
contract, liability cap, arbitration clause, or guaranteed support commitment.
These are recommended scope choices, not mandatory boilerplate.

## Provider requirements and scope

Enable Banking explains that privacy and terms URLs describe how the receiving
application uses data. Its FAQ exempts restricted own-account activation from
checking those URLs and the contact email; this is not confirmation that an
arbitrary document is suitable. Publishing accurate, accessible Markdown is
the proposed approach, not a verified provider approval.
[Enable Banking FAQ](https://enablebanking.com/docs/faq/#why-are-a-data-protection-email-and-links-to-app-terms-and-privacy-required-in-production).

Its terms require accurate application information and secure credentials.
Personal production use is limited to the linked accounts belonging to the
control-panel user. Separate installations should therefore use separate
registrations and credentials; these documents do not authorize a shared
bank-data service. The provider's agreement remains separate from Budget's
terms. [Enable Banking terms](https://enablebanking.com/terms/).

## Boundaries before wider use

GDPR Article 2(2)(c) excludes purely personal or household processing; Recital
18 distinguishes providers enabling that processing. Do not generalize this
into an exemption for hosting other people's data. Where GDPR applies, Articles
13–14 require additional contextual information, including applicable legal
basis, rights, transfers and data sources. A template does not establish those
facts. Reassess the notice when the audience or processing changes.
[GDPR](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng).

Before registration, the operator must supply a reachable data-protection email
and confirm that the published notice matches the installation. Do not invent
an address, a retention period, consent controls, encryption guarantees, or a
live bank connector to fill a template.
