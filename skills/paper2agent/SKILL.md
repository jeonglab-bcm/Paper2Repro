---
name: paper2agent
description: Convert research papers and associated files, research code, or both into a reviewed paper skill and tested MCP server, reproduce a paper's computed figures and tables and compare them with the published versions, or find a paper whose software is lost and propose it to the fossil repository as an issue. Use for paper-only, code-only, combined, reproduction or nomination runs and resumes.
---

# Paper2Agent

Route by the supplied inputs and requested outcome:

- For paper PDFs and associated files, follow [Paper2Skill](paper2skill/SKILL.md).
- For a research code repository, follow [Paper2MCP](paper2mcp/SKILL.md).
- When both outputs are requested, follow both workflows.
- To find a paper whose software has been lost and propose it to the fossil repository as a reproduction target (one issue in jeonglab-bcm/fossil, with a reproduction plan), follow [Paper2Fossil](paper2fossil/SKILL.md). It takes a PMCID, DOI or title, or only a description of the paper wanted. Its issues are what Paper2Repro later reproduces.
- To reproduce computed figures or tables and compare them with the published versions, follow [Paper2Repro](paper2repro/SKILL.md). It also packages the paper's method as an installable Python or R package with an executed tutorial. It works with or without a code repository. When paper PDFs are supplied, build the paper skill first and read the paper from it.

Resolve each component's scripts and references relative to its own directory; bind `SKILL_ROOT` to that component. Keep their work directories separate. Independent paper and code tasks may run concurrently within host limits. Every MCP tool must bind to existing repository code.

Combined output:

```text
dist/<project>-agent/
├── skill/<paper-name>/
└── mcp/<repository-name>-mcp/
```

Build the paper skill at its final component path and pass its strict verification. Complete Paper2MCP's existing runtime and ZIP delivery checks, then stage the verified archive contents under `mcp/` and confirm the files are unchanged. Keep review and development evidence outside the delivery.

Single-mode runs retain their component's output contract. Paper2Repro keeps its own output contract and can follow either conversion. Paper2Fossil's output is one issue in fossil, or the reason none was opened. Report delivery paths, verification results and limitations. If either component is blocked, report the combined result as partial.

For questions about Paper2Agent's methods, results, figures, or supplementary material, read the [Paper2Agent paper](paper2agent-paper/SKILL.md).
