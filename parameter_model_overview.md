# Parameter Model Overview

## Core object relationships

```mermaid
flowchart TD
    A[Param._instances] --> B[Param objects]
    B --> C{validate()}
    C --> D[parse formula identifiers]
    D --> E{identifier is allowed keyword?}
    E -->|No| F{identifier matches a real Param name?}
    F -->|No| G[status = Error]
    F -->|Yes| H[valid]
    G --> I[validation_message]

    J[Schedule._instances] --> K[Schedule objects]
    K --> L[self.fams]
    L --> M[Fam objects]
    M --> N[self.params]
    N --> O[Param objects]

    M --> P{Fam.validate()}
    P --> Q[family has name?]
    Q -->|No| R[Error]
    Q -->|Yes| S[check formula refs in family params]
    S --> T{any ref not in family_param_names?}
    T -->|Yes| U[Error]
    T -->|No| V[Ready]

    K --> W{Schedule.validate()}
    W --> X[loop fams]
    X --> Y{fam.status == Error?}
    Y -->|Yes| Z[aggregate family errors]
    Y -->|No| AA[continue]
    Z --> AB[status = Error]

    AC[ParameterManagerState] --> AD[pickle checkpoint]
    AD --> AE[schedule.to_dict()]
    AE --> AF[Schedule.from_dict()]
    AF --> AG[rebuild object graph]
```

## Current storage model

This project does not yet use a real database. The live data is stored in memory through Python object references:

- `Param._instances` stores all parameter objects
- `Schedule._instances` stores all schedule objects
- `Schedule.fams` stores family objects
- each `Fam` stores its own `params` and `overrides`
- `ParameterManagerState.save()` serializes the schedule to a local pickle file

Relevant code:

- [revit-parameter-manager.py](revit-parameter-manager.py#L7-L39)
- [revit-parameter-manager.py](revit-parameter-manager.py#L251-L443)
- [revit-parameter-manager.py](revit-parameter-manager.py#L444-L557)
- [revit-parameter-manager.py](revit-parameter-manager.py#L559-L585)

## How validation works

### `Param.validate()`

In [revit-parameter-manager.py](revit-parameter-manager.py#L120-L167), `Param.validate()`:

1. reads the formula
2. strips quoted strings
3. extracts identifiers
4. checks each identifier against:
   - allowed formula functions such as `ABS`, `MAX`, and `IF`
   - the live set of known parameter names from `Param._instances`

If an identifier is neither, it marks the parameter as `Error`.

### `Fam.validate()`

In [revit-parameter-manager.py](revit-parameter-manager.py#L275-L318), `Fam.validate()`:

1. confirms the family has a name
2. confirms it contains parameters
3. checks each parameter formula
4. compares referenced identifiers with:
   - known global parameter names
   - the family’s own parameter names

If a formula references a parameter that exists globally but is not attached to that family, it flags the family as invalid.

### `Schedule.validate()`

In [revit-parameter-manager.py](revit-parameter-manager.py#L483-L501), `Schedule.validate()`:

1. iterates through each family in `self.fams`
2. calls `fam.validate()`
3. rolls up any family errors into the schedule status

So the schedule is a summary validator and aggregator, rather than the original source of truth.

## How overrides are checked

Overrides are stored in memory on the model objects rather than in a database table:

- `Fam.overrides` holds override dictionaries by parameter name
- `Fam.override_param(...)` validates allowed keys with `Param.validate_overrides(...)`
- `Schedule.override_param(...)` applies overrides across families and refreshes the flattened params list

Relevant code:

- [revit-parameter-manager.py](revit-parameter-manager.py#L350-L365)
- [revit-parameter-manager.py](revit-parameter-manager.py#L520-L557)

## Persistence

The only persistence mechanism currently in use is the checkpoint file created by `ParameterManagerState`:

- [revit-parameter-manager.py](revit-parameter-manager.py#L559-L585)

It saves:

- `version`
- `schedule`: `self.schedule.to_dict()`

and reloads with `Schedule.from_dict(...)`.

## Short summary

The current architecture is:

- live in-memory object graph
- validation performed by object methods
- checkpoint persistence via pickle
- no separate database table/query layer yet

This gives you a model-first validation setup where the core objects are the source of truth, and the UI simply reflects that state.
