## ADDED Requirements

### Requirement: Managed / ad-hoc provenance badge
Each skill SHALL carry a provenance source in `skill_provenance` (`source ∈ {managed, adhoc}`). UI upload/create SHALL produce an `adhoc` skill; skills compiled by askit `deploy --target fleetent` from a spec / `SKILL.md` SHALL be `managed`. The list SHALL display the corresponding badge.

#### Scenario: UI-created skill is ad-hoc
- **WHEN** an admin uploads or creates a skill in the UI
- **THEN** its `skill_provenance.source` is `adhoc` and the list shows an "ad-hoc" badge

#### Scenario: Deployed skill is managed
- **WHEN** a skill is recorded as compiled by askit `deploy --target fleetent`
- **THEN** its `skill_provenance.source` is `managed` and the list shows a "managed" badge

### Requirement: Drift marking on managed skills
A UI change to a managed skill SHALL be treated as a runtime override and SHALL set `drift=1`, marking the skill as drifted in the list. Reverting via the override-reflow flow SHALL clear the drift mark.

#### Scenario: Editing a managed skill marks drift
- **WHEN** an admin edits a `managed` skill in the UI
- **THEN** the skill's `drift` is set to `1` and the list marks it as drifted

### Requirement: Override reflow hooks
The system SHALL expose hooks to feed drift into the askit override-reflow flow (`override sync` capture, `promote` to spec, `discard` to be overwritten on next deploy). The actual reflow semantics belong to the askit domain; this surface only marks drift and triggers reflow.

#### Scenario: Promote drift to spec
- **WHEN** an admin reviews a drifted managed skill's diff and chooses promote
- **THEN** the surface triggers the askit promote flow and the action is audited

#### Scenario: Discard drift
- **WHEN** an admin chooses discard for a drifted managed skill
- **THEN** the surface triggers the askit discard flow, signalling the change will be overwritten by spec on next deploy, and the action is audited

### Requirement: Immutable fields restored by spec
Fields marked immutable (aligned with askit IMMUTABLE_FILES) on a managed skill SHALL be restored from spec on the next deploy even if changed in the UI; the UI SHALL surface a clear notice for such fields.

#### Scenario: Immutable field edit warned
- **WHEN** an admin edits an immutable field of a managed skill
- **THEN** the response includes a notice that the field will be restored from spec on the next deploy
