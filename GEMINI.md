# Second Life Creator Suite - Workspace Guidelines

## Mandatory Living Architecture & Knowledge Base Updates
`docs/ARCHITECTURE_AND_KNOWLEDGE_BASE.md` is a **strictly maintained living engineering codex**. Whenever an agent:
- Adds a new operator, tool, module, generator, or user-facing feature
- Formulates, modifies, or calibrates mathematical algorithms or coordinate pipelines
- Discovers or resolves a bug, platform quirk, or false diagnosis ("culprit trap")
- Alters DevKit conventions, visibility rules, shader graphs, or packaging systems

**The agent MUST update `docs/ARCHITECTURE_AND_KNOWLEDGE_BASE.md` BEFORE committing code or closing the turn.**
1. Document the architectural principles, formulas, and code paths in the appropriate technical section.
2. If a false diagnosis was debunked, add it to Section 2 (*Forensic Truth vs. "False Solution" Traps*).
3. Log the change in Section 9 (*Architecture Evolution & Changelog*).

---

## Mandatory Addon Sync, Testing & GitHub Synchronization
Whenever source files in `src/sl_pbr_exporter/`, `blender_manifest.toml`, scripts, tests, or documentation are added, modified, or deleted:

### 1. Unified 1-Step Sync (Recommended)
You can run the unified sync script which automatically builds packages, deploys locally to Blender 3.6 & 5.2, executes the 65 headless unit tests, and commits & pushes to GitHub in one command:
```powershell
python scripts/sync_repo.py "feat(scope): concise description of changes"
```

---

### 2. Manual Step-by-Step Procedure (Alternative)
If running steps individually:

1. **Rebuild & Deploy Locally**:
   ```powershell
   python scripts/deploy_to_blender.py
   ```
   Syncs directly to:
   * **Blender 3.6**: `%APPDATA%\Blender Foundation\Blender\3.6\scripts\addons\sl_pbr_exporter`
   * **Blender 5.2**: `%APPDATA%\Blender Foundation\Blender\5.2\extensions\user_default\sl_pbr_exporter`

2. **Verify Tests**:
   Ensure headless tests pass before finishing:
   ```powershell
   & "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background --python tests/run_tests.py
   ```

3. **Mandatory GitHub Push (Never Desync)**:
   Every change made to this codebase MUST be committed and pushed to GitHub before ending the turn. Never leave unpushed commits or an uncommitted working tree:
   ```powershell
   git status
   git add .
   git commit -m "<concise conventional commit message>"
   git push origin main
   ```
   If a new version release is warranted, tag and push the tag:
   ```powershell
   git tag -f -a v<version> -m "Release v<version>"
   git push -f origin v<version>
   ```

4. **Notify User to Reload**:
   Always remind the user to reload the scripts in their active Blender session:
   * Press `F3` -> `Reload Scripts` (`bpy.ops.script.reload()`), OR
   * Restart Blender if UI/operator classes were fundamentally re-registered.
