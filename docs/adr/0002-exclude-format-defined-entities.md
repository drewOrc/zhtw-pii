# 0002: Exclude format-defined entities from v1

## Context

Taiwan ID numbers, unified business numbers, phone numbers, emails, and
credit card numbers all follow fixed formats with public checksum rules.
A regex plus checksum validator catches these at close to 100% precision
and recall without any machine learning.

## Decision

v1 only models PERSON, ADDRESS, and ORG: the three entity types that have
no fixed format and therefore require a model to disambiguate from
surrounding text (a surname that is also a common word, a company name
that looks like a person's name). Format-defined entities are only used
to sanity-check that the regex baseline works on the test set, not as
part of the main evaluation.

## Consequences

The benchmark and the model both look "worse" than a tool that reports one
combined score across all entity types, because we excluded the entities
that are easiest to get right. We accept that tradeoff because a combined
score inflated by regex-solvable entities would hide whether the
ML-relevant part of the problem is actually solved.
