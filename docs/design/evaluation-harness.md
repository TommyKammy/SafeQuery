# Evaluation Harness

## Purpose

This document defines the baseline evaluation harness for SafeQuery as an application-owned capability independent from any one SQL generation engine.

## Evaluation Goals

The harness exists to answer these questions:

- does the current adapter produce usable SQL for approved scenarios
- does the guard deny unsafe or out-of-policy SQL correctly
- do model, prompt, or schema changes cause regressions
- can the team compare adapter variants without changing the control plane

## Evaluation Assets

The application should own versioned evaluation assets such as:

- representative natural language prompts
- expected answer behavior
- expected deny behavior
- regression scenarios
- schema snapshot versions used during evaluation

## Scenario Taxonomy

The baseline taxonomy should distinguish at least:

- happy-path answer scenarios
- deny-path safety scenarios
- parser-failure and unsupported-syntax safety scenarios
- authorization and dataset-governance scenarios
- approval-expiry scenarios
- retrieval-governance and citation scenarios
- analyst narrative grounding scenarios
- schema-drift regression scenarios
- replay or invalidation scenarios

## Future Family Activation Checklist

Future source families or flavors remain planned until the application-owned
evaluation assets include source-aware scenarios for:

- positive read-only outcomes
- safety deny outcomes
- connector-selection denies
- candidate lifecycle revalidation
- runtime timeout, cancellation, and kill-switch behavior
- source-aware audit artifact reconstruction
- release-gate reconstruction
- operator-history implications

Each scenario must carry source identity, source family, source flavor, dataset
contract version, schema snapshot version, execution policy version, connector
profile version, dialect profile version, expected outcome, and expected primary
deny code when the outcome is a rejection.

Dialect, connector, or profile version drift must be represented as an explicit
evaluation scenario and must fail closed when the observed artifact no longer
matches the planned profile version.

MLflow exports, search or analyst outputs, and adapter traces are supplemental
engineering artifacts. They may help explain a run, but they cannot satisfy
authoritative evaluation coverage, audit coverage, or release-gate
reconstruction for a future family or flavor. Release gates must remain
reconstructable from SafeQuery-owned evaluation outcomes and source-aware audit
events.

## Gold Answer Representation

Gold answers may be represented through:

- executable reference query or reference result set
- answer-level assertions such as row count or key field expectations
- expected deny code for blocked scenarios
- expected cited asset identifiers or citation families
- expected evidence-label behavior for analyst responses

Exact SQL string match is optional and should not be the sole correctness measure.

## Baseline Success Dimensions

The baseline evaluation dimensions are:

- execution match
- answer correctness
- deny correctness
- regression stability
- retrieval relevance when governed search is enabled
- citation correctness when analyst or search outputs cite assets
- explanation groundedness when analyst narrative is enabled
- evidence-to-narrative consistency when executed evidence is rendered

The system should not depend only on exact SQL text matching, because semantically correct SQL may vary across adapters or prompt versions.

## Pilot Entry Thresholds

The baseline pilot thresholds are:

- critical deny corpus: 100 percent pass
- execution match on executable positive scenarios: at least 90 percent
- answer correctness on pilot-priority scenarios: at least 85 percent
- regression stability for critical safety scenarios: zero newly introduced failures
- citation correctness for executed-evidence claims: 100 percent on critical scenarios
- evidence-to-narrative consistency for critical analyst scenarios: 100 percent pass

Parser-failure and unsupported-syntax deny scenarios are part of the critical safety subset and must fail closed with the expected deny codes.

Approval-expiry denial scenarios are also part of the critical safety subset and must return the expected expiry deny code.

## Manual Review Rules

Manual review is required when:

- the scenario produces a semantically acceptable answer through a non-reference query shape
- the model output is partially correct but below automated threshold
- deny outcome is correct but deny code differs from the expected family
- retrieved assets are semantically acceptable but differ from the reference set
- analyst narrative is useful but groundedness scoring is borderline
- a threshold miss would otherwise block release or pilot progression

## When to Run Evaluations

At minimum, run evaluations when:

- adapter implementation changes
- prompt or model version changes
- schema context changes
- SQL Guard behavior changes

## Reporting Expectations

Evaluation output should make it easy to compare runs by:

- scenario
- adapter version
- model or prompt version
- schema snapshot version
- retrieval corpus version where applicable
- pass or fail by evaluation dimension
- expected and observed deny code where relevant
- expected and observed cited asset identifiers where relevant

## Relation to Production Auditing

Evaluation assets and results are application-owned but distinct from user audit logs. They should support engineering quality and regression review without becoming a shadow audit system for end-user activity.

## Recommended Tooling

MLflow is the recommended backend for:

- storing evaluation runs
- comparing prompt, model, and retrieval variants
- tracing retrieval and analyst workflows
- linking model or experiment lineage to regression outcomes

Using MLflow here does not change the SafeQuery trust boundary. It is an engineering support system rather than the authoritative audit or execution-governance store.
