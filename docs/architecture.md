# SweetyStoryLab – Architecture Brief

## Project Vision

SweetyStoryLab is not a Horror Lab automation.

It is a reusable AI Storytelling Platform that can generate, assemble, and publish evergreen storytelling content across multiple brands from a single shared codebase.

Examples of future brands include:

* Horror Lab
* Mystery Archive
* Bible Stories
* History Files
* Animal Tales
* Space Mysteries

The engine should never know which storytelling genre it is producing.

Genres are configuration.

The engine provides behavior.

---

# Architecture Philosophy

This project is platform-first, not brand-first.

Every architectural decision should answer:

> "Will this still work if I have 50 brands?"

The objective is to build reusable systems rather than one-off features.

---

# Current Milestone

## Architecture Validation

The current milestone is **not** launching Mystery Archive.

The goal is to prove that the architecture is correctly separated into generic engine code and brand-specific configuration.

---

# Pass Criteria

The milestone succeeds only if all three conditions are met.

### 1. Horror Lab parity

Refactor the current Horror Lab implementation into:

* core/
* brands/horror_lab/

without changing its behavior.

The generated output should be indistinguishable from the current production output.

---

### 2. Add Mystery Archive

Mystery Archive should be added using only:

* configuration
* prompts
* assets
* secrets

No engine behavior should be modified.

---

### 3. Zero core changes

Adding Mystery Archive must not require edits to:

* renderers
* pipeline
* publisher
* FFmpeg assembly
* TTS pipeline
* orchestration

If supporting Mystery Archive requires modifying core behavior, treat that as evidence that the abstraction boundary is incorrect.

Revisit the architecture instead of introducing a special case.

---

# Core vs Brand

## Core owns behavior

Core is responsible for:

* Story Engine
* Renderer Registry
* Video Assembly
* Audio Generation
* Publisher
* Scheduler
* Logging
* Provider Interfaces

Core should be genre-agnostic.

---

## Brands own identity

Each brand owns:

* prompts
* branding
* colors
* logos
* hashtags
* topic source
* voice selection
* posting schedule
* secrets reference
* platform configuration

Adding a new brand should require creating a new brand folder rather than modifying engine code.

---

# Story Model

The Story Engine should work from an ordered segment template.

Example:

```yaml
segment_template:
  - narration_scene
  - narration_scene
  - narration_scene
  - question_slide
```

The engine renders segments according to their registered renderer.

Brands decide which segment types appear and in what order.

---

# Renderer Registry

Renderers implement reusable behaviors.

Examples include:

* narration_scene
* question_slide

New renderer types should only be introduced when a genuinely new rendering behavior is required.

Do not introduce new renderer types simply because a new brand exists.

---

# Mystery Archive (Validation Brand)

Mystery Archive exists primarily to validate the architecture.

Initial characteristics:

* Cold-case documentary style
* English
* Educational tone
* Avoid speculation and present theories responsibly
* Same segment template as Horror Lab
* Same closing mechanic (question_slide)

The objective is to prove that changing only configuration and prompts is sufficient.

---

# Secrets

Sensitive values should never live inside brand configuration.

Brand configuration should reference secret names.

Example:

* HORROR_FB_PAGE_TOKEN
* MYSTERY_FB_PAGE_TOKEN

The publisher should support a dry-run mode when credentials are absent or placeholders, allowing the pipeline to complete through video generation without failing.

---

# Development Principles

* Extract, don't rewrite.
* Preserve behavior before adding features.
* Validate abstractions before extending them.
* Configuration over hardcoding.
* Reuse over duplication.
* Delay complexity until justified.
* Avoid premature abstraction.
* If an abstraction fails, redesign it rather than patching it with special cases.

---

# Claude's Role

Act as Lead Software Architect.

Prioritize architecture over implementation.

When extracting code:

* preserve existing behavior,
* identify hidden genre-specific assumptions,
* document architectural concerns,
* explain design decisions,
* and produce an assumption audit alongside the refactor.

The objective is not simply to refactor Horror Lab.

The objective is to establish SweetyStoryLab as a reusable storytelling platform with a clean, extensible architecture.
