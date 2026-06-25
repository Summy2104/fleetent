from pathlib import Path


def test_knowledge_base_capability_docs_describe_advanced_file_parsers():
    content = Path("docs/capabilities/knowledge-base.md").read_text(encoding="utf-8")

    required_phrases = [
        "PDF / DOCX / PPTX / XLSX",
        "Google Sheets",
        "Google Slides",
        "parser registry",
        "OCR",
        "VLM",
        "扫描 PDF",
        "不支持",
    ]
    for phrase in required_phrases:
        assert phrase in content


def test_owner_roadmap_marks_advanced_file_parsers_complete():
    content = Path("docs/roadmaps/intelligence-roadmap.md").read_text(encoding="utf-8")

    assert "`knowledge-base-file-parsers-advanced`：已完成" in content


def test_pilot_capability_verification_report_is_documented():
    roadmap = Path("docs/roadmaps/pilot-readiness-roadmap.md").read_text(encoding="utf-8")
    acceptance = Path("docs/operations/pilot-acceptance-guide.md").read_text(encoding="utf-8")
    runbook = Path("docs/operations/pilot-runbook.md").read_text(encoding="utf-8")

    required = [
        "uv run python scripts/generate_pilot_verification_report.py",
        "pilot-capability-verification.md",
        "pilot-capability-verification.json",
        "FLEETENT_REAL_LLM_SMOKE",
        "FLEETENT_GOOGLE_DRIVE_SMOKE",
        "Pilot blocker",
        "Conditional Go",
    ]
    for phrase in required:
        assert phrase in roadmap
        assert phrase in acceptance
        assert phrase in runbook


def test_capability_docs_describe_entity_extraction():
    kb_doc = Path("docs/capabilities/knowledge-base.md").read_text(encoding="utf-8")
    roadmap = Path("docs/roadmaps/intelligence-roadmap.md").read_text(encoding="utf-8")

    for content in [kb_doc, roadmap]:
        assert "entity extraction" in content
        assert "kb_entities" in content
        assert "graph evidence" in content


def test_capability_docs_describe_graph_search_scope():
    kb_doc = Path("docs/capabilities/knowledge-base.md").read_text(encoding="utf-8")
    roadmap = Path("docs/roadmaps/intelligence-roadmap.md").read_text(encoding="utf-8")

    for content in [kb_doc, roadmap]:
        assert "graph_search" in content
        assert "depth 0/1" in content
        assert "graph evidence" in content
        assert "独立于 search" in content
        assert "不接 query planner / rerank" in content


def test_capability_docs_describe_query_planner_scope():
    kb_doc = Path("docs/capabilities/knowledge-base.md").read_text(encoding="utf-8")
    roadmap = Path("docs/roadmaps/intelligence-roadmap.md").read_text(encoding="utf-8")

    for content in [kb_doc, roadmap]:
        assert "plan_knowledge_search" in content
        assert "execute_knowledge_search_plan" in content
        assert "规则型" in content
        assert "不改 `search()`" in content
        assert "不接 LLM planner" in content


def test_capability_docs_describe_kb_reflection_reports_scope():
    reflection_doc = Path("docs/capabilities/reflection.md").read_text(encoding="utf-8")
    kb_doc = Path("docs/capabilities/knowledge-base.md").read_text(encoding="utf-8")
    roadmap = Path("docs/roadmaps/intelligence-roadmap.md").read_text(encoding="utf-8")

    for content in [reflection_doc, kb_doc, roadmap]:
        assert "run_kb_reflection_report" in content
        assert "reflection_reports(domain=knowledge_base)" in content
        assert "missing_knowledge" in content
        assert "connector_sync_issue" in content
        assert "只读报告" in content
        assert "不自动写 KB" in content
        assert "不触发 sync" in content


def test_capability_docs_describe_skill_reflection_proposals_scope():
    reflection_doc = Path("docs/capabilities/reflection.md").read_text(encoding="utf-8")
    skill_doc = Path("docs/capabilities/skill.md").read_text(encoding="utf-8")
    roadmap = Path("docs/roadmaps/intelligence-roadmap.md").read_text(encoding="utf-8")

    for content in [reflection_doc, skill_doc, roadmap]:
        assert "SkillProposal" in content
        assert "reflection_proposals(domain=skill)" in content
        assert "create_skill" in content
        assert "update_skill" in content
        assert "deprecate_skill" in content
        assert "pending" in content
        assert "不自动改 skill" in content


def test_capability_docs_describe_agent_memory_scope():
    memory_doc = Path("docs/capabilities/memory.md").read_text(encoding="utf-8")
    long_term_doc = Path("docs/capabilities/long-term-ctx.md").read_text(encoding="utf-8")
    roadmap = Path("docs/roadmaps/intelligence-roadmap.md").read_text(encoding="utf-8")

    for content in [memory_doc, long_term_doc, roadmap]:
        assert "Shared Memory" in content
        # Shared/Agent Memory prompt injection is governed by the long-term-ctx context policy.
        assert "context policy" in content

    # The agent-memory rescope renamed shared memory to agent-level Agent Memory
    # (the team/tenant scope was dropped): memory.md describes the migrated surface,
    # storage table, and vector namespace.
    assert "Agent Memory" in memory_doc
    assert "agent_memory_items" in memory_doc
    assert "agentmem:" in memory_doc
